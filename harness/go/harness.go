// Go harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
//
// Go cannot call a function by name at runtime, so build.go compiles this file together with a
// generated table of the steps file's functions, `steps`, and `stepNames` in file order.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"reflect"
	"runtime/debug"
	"strconv"
	"strings"
)

type request struct {
	ID            json.RawMessage   `json:"id"`
	Command       string            `json:"command"`
	Step          string            `json:"step"`
	Args          []json.RawMessage `json:"args"`
	Client        *string           `json:"client"`
	ReturnsClient bool              `json:"returnsClient"`
}

// HarnessError reports a step the harness could not call, e.g. with the wrong arguments.
type HarnessError string

func (e HarnessError) Error() string { return string(e) }

var errorType = reflect.TypeFor[error]()

func main() {
	clients := map[string]reflect.Value{}
	in := bufio.NewReader(os.Stdin)
	// os.Stdout is unbuffered, so every response is flushed as soon as it is encoded.
	out := json.NewEncoder(os.Stdout)
	out.SetEscapeHTML(false)

	for {
		line, err := in.ReadBytes('\n')
		if len(bytes.TrimSpace(line)) > 0 {
			var req request
			if err := json.Unmarshal(line, &req); err != nil {
				fmt.Fprintf(os.Stderr, "harness: invalid request: %v\n", err)
				os.Exit(1)
			}
			if err := out.Encode(handle(req, clients)); err != nil {
				fmt.Fprintf(os.Stderr, "harness: writing response: %v\n", err)
				os.Exit(1)
			}
		}
		if err == io.EOF {
			return
		} else if err != nil {
			fmt.Fprintf(os.Stderr, "harness: reading stdin: %v\n", err)
			os.Exit(1)
		}
	}
}

func handle(req request, clients map[string]reflect.Value) map[string]any {
	response := map[string]any{"id": req.ID}
	if req.Command == "hello" {
		response["steps"] = stepNames
		return response
	}
	step, ok := steps[req.Step]
	if !ok {
		response["missing"] = true
		return response
	}

	var args []reflect.Value
	if req.Client != nil {
		client, ok := clients[*req.Client]
		if !ok {
			response["error"] = describe(HarnessError("no client " + *req.Client))
			return response
		}
		args = append(args, client)
	}
	result, err := call(reflect.ValueOf(step), args, req.Args)
	if err != nil {
		fmt.Fprintf(os.Stderr, "harness: %s: %v\n", req.Step, err)
		response["error"] = describe(err)
	} else if req.ReturnsClient {
		handle := strconv.Itoa(len(clients) + 1)
		clients[handle] = result
		response["client"] = handle
	} else if result.IsValid() {
		response["result"] = result.Interface()
	} else {
		response["result"] = nil
	}
	return response
}

// call converts the JSON arguments to the step function's parameter types, after any leading
// arguments, and calls it. A trailing error result is returned as the error, and a panic is
// reported as an error too.
func call(fn reflect.Value, args []reflect.Value, jsonArgs []json.RawMessage) (result reflect.Value, err error) {
	fnType := fn.Type()
	if fnType.NumIn() != len(args)+len(jsonArgs) {
		return result, HarnessError(fmt.Sprintf(
			"the step function takes %d arguments, but the runner sent %d", fnType.NumIn(), len(args)+len(jsonArgs),
		))
	}
	for _, raw := range jsonArgs {
		arg, err := convert(raw, fnType.In(len(args)))
		if err != nil {
			return result, err
		}
		args = append(args, arg)
	}
	for i, arg := range args {
		if !arg.Type().AssignableTo(fnType.In(i)) {
			return result, HarnessError(fmt.Sprintf("argument %d is a %s, not a %s", i+1, arg.Type(), fnType.In(i)))
		}
	}

	defer func() {
		if r := recover(); r != nil {
			fmt.Fprintf(os.Stderr, "panic: %v\n%s", r, debug.Stack())
			err = panicError{r}
		}
	}()
	results := fn.Call(args)
	if n := len(results); n > 0 && fnType.Out(n-1) == errorType {
		if e := results[n-1].Interface(); e != nil {
			return result, e.(error)
		}
		results = results[:n-1]
	}
	if len(results) > 0 {
		result = results[0]
	}
	return result, nil
}

// convert decodes a JSON argument into the parameter type. JSON values held in interfaces
// (`any`, `map[string]any`) keep their types: numbers become int64 or float64, not json.Number.
func convert(raw json.RawMessage, to reflect.Type) (reflect.Value, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return reflect.Value{}, err
	}
	if v := reflect.ValueOf(normalise(value)); v.IsValid() && v.Type().AssignableTo(to) {
		return v, nil
	}
	target := reflect.New(to)
	if err := json.Unmarshal(raw, target.Interface()); err != nil {
		return reflect.Value{}, HarnessError(fmt.Sprintf("cannot convert %s to %s: %v", raw, to, err))
	}
	return target.Elem(), nil
}

func normalise(value any) any {
	switch v := value.(type) {
	case json.Number:
		if i, err := v.Int64(); err == nil {
			return i
		}
		f, _ := v.Float64()
		return f
	case map[string]any:
		for key, item := range v {
			v[key] = normalise(item)
		}
	case []any:
		for i, item := range v {
			v[i] = normalise(item)
		}
	}
	return value
}

// panicError reports a step that panicked.
type panicError struct{ value any }

func (e panicError) Error() string { return fmt.Sprint(e.value) }

// describe formats an error as "<type>: <message>", e.g. "flagsmith.FlagsmithClientError: …".
func describe(err error) string {
	if p, ok := err.(panicError); ok {
		return fmt.Sprintf("panic: %s: %v", typeName(p.value), p.value)
	}
	return typeName(err) + ": " + err.Error()
}

func typeName(value any) string {
	return strings.TrimPrefix(fmt.Sprintf("%T", value), "*")
}
