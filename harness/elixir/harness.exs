# Elixir harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
#
# Usage, from the SDK's Mix project: mix run harness.exs path/to/steps.exs
#
# Requires Jason, which the SDK is expected to depend on.

defmodule SDKSpec.Harness do
  @marker ~r/^\s*#+\s*(When .+?|Create the SDK client.*?)\s*$/
  @function ~r/^\s*def\s+([a-z_][a-zA-Z0-9_]*[?!]?)/

  def main([path]) do
    # Responses are the only thing written to stdout. Everything else, including
    # the SDK's own output and logs, goes to stderr.
    stdio = Process.group_leader()
    Process.group_leader(self(), Process.whereis(:standard_error))
    log_to_stderr()

    steps = load_steps(path)
    loop(stdio, steps, %{})
  end

  defp log_to_stderr do
    {:ok, handler} = :logger.get_handler_config(:default)
    :ok = :logger.remove_handler(:default)
    config = Map.put(handler.config, :type, :standard_error)

    :ok =
      :logger.add_handler(:default, handler.module, %{
        handler
        | config: Map.drop(config, [:file_check, :max_no_bytes, :max_no_files])
      })
  end

  # Maps each step's text to the {module, function} marked with it.
  defp load_steps(path) do
    modules = for {module, _bytecode} <- Code.require_file(path), do: module

    path
    |> File.read!()
    |> String.split("\n")
    |> Enum.reduce({%{}, nil}, fn line, {steps, pending} ->
      case {Regex.run(@marker, line), pending && Regex.run(@function, line)} do
        {[_, marker], _} ->
          {steps, marker}

        {nil, [_, function]} ->
          name = String.to_atom(function)
          module = Enum.find(modules, &Keyword.has_key?(&1.__info__(:functions), name))
          {Map.put(steps, pending, {module, name}), nil}

        _ ->
          {steps, pending}
      end
    end)
    |> elem(0)
  end

  defp loop(stdio, steps, clients) do
    case IO.read(stdio, :line) do
      :eof ->
        :ok

      {:error, reason} ->
        exit(reason)

      line ->
        request = Jason.decode!(line)
        {response, clients} = handle(request, steps, clients)
        IO.write(stdio, [Jason.encode!(Map.put(response, "id", request["id"])), "\n"])
        loop(stdio, steps, clients)
    end
  end

  defp handle(%{"command" => "hello"}, steps, clients),
    do: {%{"steps" => Map.keys(steps)}, clients}

  defp handle(%{"step" => step} = request, steps, clients) do
    case Map.fetch(steps, step) do
      :error -> {%{"missing" => true}, clients}
      {:ok, {module, function}} -> run(module, function, request, clients)
    end
  end

  defp run(module, function, request, clients) do
    args =
      case request["client"] do
        nil -> request["args"]
        handle -> [Map.fetch!(clients, handle) | request["args"]]
      end

    case invoke(module, function, args) do
      {:error, error} ->
        {%{"error" => error}, clients}

      {:ok, result} ->
        if request["returnsClient"] do
          handle = Integer.to_string(map_size(clients) + 1)
          {%{"client" => handle}, Map.put(clients, handle, result)}
        else
          # Encode here so that unserialisable results are reported as step errors.
          case Jason.encode(result) do
            {:ok, json} -> {%{"result" => Jason.Fragment.new(json)}, clients}
            {:error, e} -> {%{"error" => describe(e)}, clients}
          end
        end
    end
  end

  # Steps return a value, `{:ok, value}` or `{:error, reason}`, or raise.
  defp invoke(module, function, args) do
    case apply(module, function, args) do
      {:ok, value} -> {:ok, value}
      {:error, reason} -> {:error, describe(reason)}
      value -> {:ok, value}
    end
  rescue
    e ->
      IO.puts(:stderr, Exception.format(:error, e, __STACKTRACE__))
      {:error, describe(e)}
  catch
    kind, reason ->
      IO.puts(:stderr, Exception.format(kind, reason, __STACKTRACE__))
      {:error, "#{kind}: #{inspect(reason)}"}
  end

  defp describe(%{__exception__: true} = e),
    do: "#{inspect(e.__struct__)}: #{Exception.message(e)}"

  defp describe(reason), do: "error: #{inspect(reason)}"
end

SDKSpec.Harness.main(System.argv())
