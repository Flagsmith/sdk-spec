<?php

/**
 * PHP harness for the Flagsmith SDK behavioural spec. See HARNESS.md.
 *
 * Usage: php harness.php path/to/steps.php
 *
 * Loads Composer's `vendor/autoload.php` from the working directory, if present, before the steps file.
 */

declare(strict_types=1);

namespace FlagsmithSdkSpec\Harness;

const MARKER = '/^\s*(?:\/\/|#)\s*((?:Given|When|Then) .+?)\s*$/';
const FUNCTION_ = '/^\s*function\s+(\w+)\s*\(/';
const NAMESPACE_ = '/^\s*namespace\s+([\w\\\\]+)\s*;/';

/**
 * Maps each step's text to the function marked with it.
 *
 * @return array<string, \ReflectionFunction>
 */
function loadSteps(string $path): array
{
    require $path;

    $steps = [];
    $namespace = '';
    $pending = null;
    foreach (file($path, FILE_IGNORE_NEW_LINES) as $line) {
        if (preg_match(NAMESPACE_, $line, $match)) {
            $namespace = $match[1] . '\\';
        } elseif (preg_match(MARKER, $line, $match)) {
            $pending = $match[1];
        } elseif ($pending !== null && preg_match(FUNCTION_, $line, $match)) {
            $steps[$pending] = new \ReflectionFunction($namespace . $match[1]);
            $pending = null;
        }
    }

    return $steps;
}

/**
 * JSON objects arrive as `stdClass`. Convert them to associative arrays for parameters typed `array`.
 */
function convertArg(mixed $arg, ?\ReflectionParameter $parameter): mixed
{
    $type = $parameter?->getType();
    if ($arg instanceof \stdClass && $type instanceof \ReflectionNamedType && $type->getName() === 'array') {
        return json_decode(json_encode($arg, JSON_PRESERVE_ZERO_FRACTION), true);
    }

    return $arg;
}

function main(array $argv): void
{
    // Keep stdout for responses: PHP errors go to stderr, and so does anything the SDK or steps echo.
    ini_set('display_errors', 'stderr');
    ob_start(static function (string $output): string {
        fwrite(STDERR, $output);

        return '';
    }, 1);

    if (is_file('vendor/autoload.php')) {
        require 'vendor/autoload.php';
    }
    $steps = loadSteps($argv[1]);
    $clients = [];

    while (($line = fgets(STDIN)) !== false) {
        $request = json_decode($line, false, 512, JSON_THROW_ON_ERROR);
        $response = ['id' => $request->id];
        $step = $request->command === 'step' ? $steps[$request->step] ?? null : null;
        if ($request->command === 'hello') {
            $response['steps'] = array_keys($steps);
        } elseif ($step === null) {
            $response['missing'] = true;
        } else {
            try {
                $args = $request->args;
                if (($request->client ?? null) !== null) {
                    array_unshift($args, $clients[$request->client] ?? throw new \OutOfBoundsException("No client {$request->client}"));
                }
                $parameters = $step->getParameters();
                foreach ($args as $i => $arg) {
                    $args[$i] = convertArg($arg, $parameters[$i] ?? null);
                }
                $result = $step->invokeArgs($args);
                if ($request->returnsClient ?? false) {
                    $response['client'] = (string) (count($clients) + 1);
                    $clients[$response['client']] = $result;
                } else {
                    $response['result'] = $result;
                }
            } catch (\Throwable $e) {
                fwrite(STDERR, "{$e}\n");
                $response['error'] = get_class($e) . ': ' . $e->getMessage();
            }
        }
        // Keep floats such as 1.0 as JSON numbers with a fractional part.
        fwrite(STDOUT, json_encode($response, JSON_THROW_ON_ERROR | JSON_PRESERVE_ZERO_FRACTION) . "\n");
        fflush(STDOUT);
    }
}

main($argv);
