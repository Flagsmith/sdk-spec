//! Generates the harness's dispatch table from the SDK's steps file. See HARNESS.md.
//!
//! Rust cannot call a function by name at runtime, so this finds every step marker in
//! `sdk-spec/steps.rs` and writes a function per step that converts the request's
//! arguments, calls the marked function and converts what it returns.

use std::env;
use std::fmt::Write;
use std::fs;
use std::path::Path;

const STEPS_FILE: &str = "../sdk/sdk-spec/steps.rs";

struct Step {
    text: String,
    function: String,
    /// The first parameter's type when it is a reference: the step uses a client.
    client: Option<Client>,
    arguments: usize,
    fallible: bool,
}

enum Client {
    Shared,
    Mutable,
}

fn main() {
    let path = Path::new(&env::var("CARGO_MANIFEST_DIR").unwrap()).join(STEPS_FILE);
    println!("cargo:rerun-if-changed={}", path.display());
    let source = fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("Cannot read the steps file {}: {e}", path.display()));

    let steps = find_steps(&source);
    let out = Path::new(&env::var("OUT_DIR").unwrap()).join("steps.rs");
    fs::write(out, generate(&steps)).unwrap();
}

/// A step marker is a line comment starting with `Given `, `When ` or `Then `.
fn marker(line: &str) -> Option<&str> {
    let text = line
        .trim()
        .strip_prefix("//")?
        .trim_start_matches('/')
        .trim();
    ["Given ", "When ", "Then "]
        .iter()
        .any(|keyword| text.starts_with(keyword))
        .then_some(text)
}

/// The name of the function defined on this line, e.g. `pub fn create_client(`.
fn function_name(line: &str) -> Option<&str> {
    let rest = line.split_once("fn ")?;
    let before = rest.0.trim();
    let is_definition = before
        .split_whitespace()
        .all(|word| word == "pub" || word == "async" || word.starts_with("pub("));
    let name_end = rest.1.find(|c: char| !(c.is_alphanumeric() || c == '_'))?;
    is_definition
        .then_some(&rest.1[..name_end])
        .filter(|name| !name.is_empty())
}

fn find_steps(source: &str) -> Vec<Step> {
    let lines: Vec<&str> = source.lines().collect();
    let mut steps = Vec::new();
    let mut pending: Option<&str> = None;
    for (i, line) in lines.iter().enumerate() {
        if let Some(text) = marker(line) {
            pending = Some(text);
        } else if let (Some(text), Some(function)) = (pending, function_name(line)) {
            steps.push(parse_signature(text, function, &lines[i..].join("\n")));
            pending = None;
        }
    }
    steps
}

/// Reads what the dispatch table needs from a function's signature, which starts `source`.
fn parse_signature(text: &str, function: &str, source: &str) -> Step {
    let open = source.find('(').unwrap();
    let mut depth = 0;
    let mut parameters = vec![String::new()];
    let mut close = open;
    for (i, c) in source[open + 1..].char_indices() {
        match c {
            '(' | '<' | '[' => depth += 1,
            ')' if depth == 0 => {
                close = open + 1 + i;
                break;
            }
            ')' | '>' | ']' => depth -= 1,
            ',' if depth == 0 => {
                parameters.push(String::new());
                continue;
            }
            _ => {}
        }
        parameters.last_mut().unwrap().push(c);
    }
    let types: Vec<&str> = parameters
        .iter()
        .filter_map(|parameter| Some(parameter.split_once(':')?.1.trim()))
        .collect();
    let client = types.first().and_then(|first| {
        if first.starts_with("&mut ") {
            Some(Client::Mutable)
        } else if first.starts_with('&') {
            Some(Client::Shared)
        } else {
            None
        }
    });

    // `-> Result<…>`, `-> flagsmith::Result<…>`, …: errors are reported to the runner.
    let after = &source[close + 1..source.find('{').unwrap_or(source.len())];
    let returns = after.trim().strip_prefix("->").unwrap_or("").trim();
    let fallible = returns
        .split('<')
        .next()
        .unwrap()
        .trim()
        .rsplit("::")
        .next()
        == Some("Result");

    Step {
        text: text.to_string(),
        function: function.to_string(),
        arguments: types.len() - usize::from(client.is_some()),
        client,
        fallible,
    }
}

fn generate(steps: &[Step]) -> String {
    let mut code = String::from("static STEPS: &[(&str, Step)] = &[\n");
    for (i, step) in steps.iter().enumerate() {
        writeln!(code, "    ({:?}, step_{i}),", step.text).unwrap();
    }
    code.push_str("];\n");

    for (i, step) in steps.iter().enumerate() {
        let mut arguments = Vec::new();
        match step.client {
            Some(Client::Shared) => arguments.push("client_ref(client)?".to_string()),
            Some(Client::Mutable) => arguments.push("client_mut(client)?".to_string()),
            None => {}
        }
        arguments.extend((0..step.arguments).map(|_| "argument(&mut args)?".to_string()));
        let mut returned = format!("steps::{}({})", step.function, arguments.join(", "));
        if step.fallible {
            returned = format!("{returned}.map_err(error)?");
        }
        // A step that does not use a client creates one (STEPS.md).
        let output = if step.client.is_some() {
            "returns_value"
        } else {
            "returns_client"
        };
        write!(
            code,
            r#"
// {text}
#[allow(unused_mut, unused_variables)]
fn step_{i}(client: Option<&mut Box<dyn Any>>, args: Vec<Value>) -> Result<Output, String> {{
    let mut args = args.into_iter();
    {output}({returned})
}}
"#,
            text = step.text,
        )
        .unwrap();
    }
    code
}
