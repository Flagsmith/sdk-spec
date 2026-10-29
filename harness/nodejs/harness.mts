/**
 * Node.js (TypeScript) harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
 *
 * Usage: node harness.mts path/to/steps.mts
 */

import { closeSync, openSync, readFileSync, writeSync } from 'node:fs';
import { resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';

type Step = (...args: unknown[]) => unknown;

const MARKER = /^\s*\/\/+\s*(When .+?|Create the SDK client.*?)\s*$/;
const FUNCTION =
    /^\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s*(\w+)|^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=/;

/**
 * Keeps stdout for protocol responses only. Libraries log to stdout in many ways, some of which
 * (e.g. pino) write to file descriptor 1 directly, so point fd 1 at stderr and answer on a copy of
 * the original stdout instead. `open` returns the lowest free descriptor, which is 1 once closed.
 */
function takeStdout(): number {
    const protocol = openSync('/dev/fd/1', 'w');
    closeSync(1);
    openSync('/dev/fd/2', 'w');
    return protocol;
}

async function loadSteps(path: string): Promise<Map<string, Step>> {
    const module = await import(pathToFileURL(path).href);

    const steps = new Map<string, Step>();
    let pending: string | undefined;
    for (const line of readFileSync(path, 'utf8').split('\n')) {
        let match: RegExpExecArray | null;
        if ((match = MARKER.exec(line))) {
            pending = match[1];
        } else if (pending && (match = FUNCTION.exec(line))) {
            const name = match[1] ?? match[2];
            if (typeof module[name] !== 'function') {
                throw new Error(
                    `The step "${pending}" is implemented by ${name}, which is not exported`
                );
            }
            steps.set(pending, module[name]);
            pending = undefined;
        }
    }
    return steps;
}

function describe(error: unknown): string {
    if (!(error instanceof Error)) {
        return `${typeof error}: ${String(error)}`;
    }
    const message = `${error.name}: ${error.message}`;
    // e.g. `TypeError: fetch failed` says little without its cause.
    return error.cause ? `${message} (caused by ${describe(error.cause)})` : message;
}

async function main(): Promise<void> {
    const out = takeStdout();
    const steps = await loadSteps(resolve(process.argv[2]));
    const clients = new Map<string, unknown>();
    const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });

    for await (const line of lines) {
        if (!line.trim()) {
            continue;
        }
        const request = JSON.parse(line);
        const response: Record<string, unknown> = { id: request.id };
        const step = request.command === 'step' ? steps.get(request.step) : undefined;
        if (request.command === 'hello') {
            response.steps = [...steps.keys()];
        } else if (!step) {
            response.missing = true;
        } else {
            const args: unknown[] = request.args;
            if (request.client != null) {
                args.unshift(clients.get(request.client));
            }
            try {
                const result = await step(...args);
                if (request.returnsClient) {
                    response.client = String(clients.size + 1);
                    clients.set(response.client as string, result);
                } else {
                    response.result = result;
                }
            } catch (error) {
                console.error(error);
                response.error = describe(error);
            }
        }
        // JSON drops `undefined`, which SDKs often use for "no value": report it as `null`.
        // `writeSync` is unbuffered, so every response is flushed as it is written.
        writeSync(out, JSON.stringify(response, (_, value) => value ?? null) + '\n');
    }
    // SDK clients may hold timers open; stdin closing ends the session.
    process.exit(0);
}

await main();
