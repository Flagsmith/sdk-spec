# frozen_string_literal: true

# Ruby harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
#
# Usage: ruby harness.rb path/to/steps.rb

require 'json'

MARKER = /\A\s*#+\s*((?:Given|When|Then) .+?)\s*\z/
FUNCTION = /\A\s*def\s+(?:self\.)?(\w+[?!]?)/

# Loads the steps file and maps each marked step's text to the method defined after it.
def load_steps(path)
  load File.expand_path(path)

  steps = {}
  pending = nil
  File.foreach(path) do |line|
    if (marker = MARKER.match(line))
      pending = marker[1]
    elsif pending && (function = FUNCTION.match(line))
      steps[pending] = TOPLEVEL_BINDING.receiver.method(function[1])
      pending = nil
    end
  end
  steps
end

def run_step(step, request, clients)
  args = request['args']
  args = [clients.fetch(request['client']), *args] unless request['client'].nil?
  result = step.call(*args)
  return { 'result' => result } unless request['returnsClient']

  handle = (clients.size + 1).to_s
  clients[handle] = result
  { 'client' => handle }
rescue StandardError => e # reported to the runner
  warn e.full_message
  { 'error' => "#{e.class}: #{e.message}" }
end

def respond(request, steps, clients)
  return { 'steps' => steps.keys } if request['command'] == 'hello'

  step = steps[request['step']]
  step ? run_step(step, request, clients) : { 'missing' => true }
end

def main
  # Keep stdout for protocol responses only: anything else written to it goes to stderr.
  out = $stdout.dup
  $stdout.reopen($stderr)

  steps = load_steps(ARGV.fetch(0))
  clients = {}

  $stdin.each_line do |line|
    request = JSON.parse(line)
    response = { 'id' => request['id'], **respond(request, steps, clients) }
    out.write("#{JSON.generate(response)}\n")
    out.flush
  end
end

main if $PROGRAM_NAME == __FILE__
