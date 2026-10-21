//! Rust harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
//!
//! Runs the SDK's steps file, `sdk-spec/steps.rs`, compiled in as the `steps` crate.
//! `build.rs` generates the dispatch table, `STEPS`, from the step markers in it.

use std::any::{type_name, Any};
use std::collections::HashMap;
use std::fmt::Display;
use std::io::{self, BufRead, Write};
use std::panic::{self, AssertUnwindSafe};

use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_json::{json, Value};

type Step = fn(Option<&mut Box<dyn Any>>, Vec<Value>) -> Result<Output, String>;

enum Output {
    Client(Box<dyn Any>),
    Value(Value),
}

include!(concat!(env!("OUT_DIR"), "/steps.rs"));

fn client_ref<T: Any>(client: Option<&mut Box<dyn Any>>) -> Result<&T, String> {
    let client: &dyn Any = &**client.ok_or("The step needs a client")?;
    client
        .downcast_ref()
        .ok_or_else(|| format!("The client is not a {}", type_name::<T>()))
}

// For steps taking `&mut Client`; unused when no step does.
#[allow(dead_code)]
fn client_mut<T: Any>(client: Option<&mut Box<dyn Any>>) -> Result<&mut T, String> {
    let client: &mut dyn Any = &mut **client.ok_or("The step needs a client")?;
    client
        .downcast_mut()
        .ok_or_else(|| format!("The client is not a {}", type_name::<T>()))
}

/// Converts the next JSON argument to the type the step function expects.
fn argument<T: DeserializeOwned>(args: &mut impl Iterator<Item = Value>) -> Result<T, String> {
    let arg = args.next().ok_or("The step was given too few arguments")?;
    serde_json::from_value(arg).map_err(error)
}

fn returns_value<T: Serialize>(value: T) -> Result<Output, String> {
    serde_json::to_value(value)
        .map(Output::Value)
        .map_err(error)
}

fn returns_client<T: Any>(client: T) -> Result<Output, String> {
    Ok(Output::Client(Box::new(client)))
}

fn error<E: Display>(e: E) -> String {
    format!("{}: {e}", type_name::<E>())
}

fn panic_message(payload: Box<dyn Any + Send>) -> String {
    let message = payload
        .downcast_ref::<&str>()
        .map(|message| message.to_string())
        .or_else(|| payload.downcast_ref::<String>().cloned())
        .unwrap_or_default();
    format!("panic: {message}")
}

fn respond(
    request: &Value,
    clients: &mut HashMap<String, Box<dyn Any>>,
) -> serde_json::Map<String, Value> {
    let mut response = serde_json::Map::new();
    response.insert("id".into(), request["id"].clone());
    if request["command"] == "hello" {
        let steps: Vec<&str> = STEPS.iter().map(|(text, _)| *text).collect();
        response.insert("steps".into(), json!(steps));
        return response;
    }
    let Some((_, step)) = STEPS.iter().find(|(text, _)| request["step"] == *text) else {
        response.insert("missing".into(), json!(true));
        return response;
    };

    let args = request["args"].as_array().cloned().unwrap_or_default();
    let client = request["client"]
        .as_str()
        .map(|handle| clients.get_mut(handle));
    let output = match client {
        Some(None) => Err(format!("Unknown client: {}", request["client"])),
        Some(client) => run(*step, client, args),
        None => run(*step, None, args),
    };
    let returns_client = request["returnsClient"] == true;
    match output {
        Ok(Output::Client(client)) if returns_client => {
            let handle = (clients.len() + 1).to_string();
            clients.insert(handle.clone(), client);
            response.insert("client".into(), json!(handle));
        }
        Ok(Output::Value(value)) if !returns_client => {
            response.insert("result".into(), value);
        }
        Ok(_) => {
            let expected = if returns_client {
                "a client"
            } else {
                "a result"
            };
            response.insert(
                "error".into(),
                json!(format!("The step must return {expected}")),
            );
        }
        Err(e) => {
            response.insert("error".into(), json!(e));
        }
    }
    response
}

/// Runs a step, reporting a panic as an error. The panic hook prints it to stderr.
fn run(step: Step, client: Option<&mut Box<dyn Any>>, args: Vec<Value>) -> Result<Output, String> {
    panic::catch_unwind(AssertUnwindSafe(|| step(client, args)))
        .unwrap_or_else(|payload| Err(panic_message(payload)))
}

fn main() {
    let mut clients = HashMap::new();
    for line in io::stdin().lock().lines() {
        let line = line.expect("Cannot read stdin");
        let request: Value = match serde_json::from_str(&line) {
            Ok(request) => request,
            Err(e) => {
                eprintln!("harness: ignoring invalid request {line:?}: {e}");
                continue;
            }
        };
        let response = respond(&request, &mut clients);
        let mut out = io::stdout().lock();
        writeln!(out, "{}", Value::Object(response)).expect("Cannot write stdout");
        out.flush().expect("Cannot flush stdout");
    }
}
