// Copyright 2025 The Drasi Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Drasi SSE CLI - stream query change events from a Drasi Server.
//!
//! Creates an SSE Reaction on the server, consumes the event stream, and
//! cleans up the reaction on exit, or observes an existing SSE endpoint.

mod sse;

use clap::Parser;
use futures_util::StreamExt;
use std::io::Write;
use std::path::PathBuf;
use std::time::Duration;

/// Stream SSE events from a Drasi Server query.
///
/// Creates a temporary SSE Reaction subscribed to the specified query,
/// streams events to stdout, and deletes the reaction on Ctrl-C.
#[derive(Parser, Debug)]
#[command(name = "drasi-sse-cli", version, about, long_about = None)]
struct Args {
    /// Drasi Server base URL (e.g. http://localhost:8080)
    #[arg(
        short,
        long,
        env = "DRASI_SERVER_URL",
        required_unless_present = "sse_url"
    )]
    server: Option<String>,

    /// Instance containing the query
    #[arg(
        short,
        long,
        env = "DRASI_INSTANCE_ID",
        required_unless_present = "sse_url"
    )]
    instance: Option<String>,

    /// Query ID to subscribe to
    #[arg(short, long, env = "DRASI_QUERY", required_unless_present = "sse_url")]
    query: Option<String>,

    /// Observe an existing SSE endpoint without creating or deleting a reaction
    #[arg(long, conflicts_with_all = ["server", "instance", "query", "sse_port", "sse_host"])]
    sse_url: Option<String>,

    /// Show heartbeat messages (debug mode)
    #[arg(short, long, default_value_t = false)]
    debug: bool,

    /// Log received events to a file
    #[arg(short, long)]
    log_file: Option<PathBuf>,

    /// Port for the SSE Reaction HTTP server
    #[arg(short = 'p', long, default_value_t = 8090, value_parser = clap::value_parser!(u16).range(1..))]
    sse_port: u16,

    /// Reaction bind address; use 0.0.0.0 only for intentional remote access
    #[arg(long, default_value = "127.0.0.1")]
    sse_host: std::net::IpAddr,
}

fn http_url(value: &str) -> Result<reqwest::Url, String> {
    let url = reqwest::Url::parse(value).map_err(|error| format!("Invalid URL: {error}"))?;
    if !matches!(url.scheme(), "http" | "https") || url.host_str().is_none() {
        return Err("URL must use HTTP or HTTPS and include a host".into());
    }
    if url.fragment().is_some() {
        return Err("URL must not contain a fragment".into());
    }
    Ok(url)
}

fn reaction_api_url(
    server: &str,
    instance: &str,
    reaction: Option<&str>,
) -> Result<reqwest::Url, String> {
    if instance.is_empty() || matches!(instance, "." | "..") {
        return Err("A valid instance ID is required".into());
    }
    let mut url = http_url(server)?;
    if url.query().is_some() {
        return Err("Server base URL must not contain a query string".into());
    }
    {
        let mut path = url
            .path_segments_mut()
            .map_err(|_| "Server URL cannot be used as a base".to_string())?;
        path.pop_if_empty()
            .extend(["api", "v1", "instances", instance, "reactions"]);
        if let Some(reaction) = reaction {
            path.push(reaction);
        }
    }
    Ok(url)
}

fn reaction_stream_url(server: &str, port: u16) -> Result<reqwest::Url, String> {
    let mut url = http_url(server)?;
    // The reaction owns a plain HTTP listener, separate from the Server API.
    url.set_scheme("http")
        .map_err(|_| "Cannot use the server host for SSE".to_string())?;
    url.set_port(Some(port))
        .map_err(|_| "Cannot set the SSE port".to_string())?;
    url.set_path("/events");
    url.set_query(None);
    Ok(url)
}

async fn response_error(resp: reqwest::Response, operation: &str) -> String {
    let status = resp.status();
    match resp.text().await {
        Ok(text) => format!("{operation} ({status}): {text}"),
        Err(error) => format!("{operation} ({status}); could not read response: {error}"),
    }
}

fn reaction_config(
    reaction_id: &str,
    query_id: &str,
    sse_port: u16,
    sse_host: std::net::IpAddr,
) -> serde_json::Value {
    serde_json::json!({
        "kind": "sse",
        "id": reaction_id,
        "queries": [query_id],
        "autoStart": true,
        "host": sse_host.to_string(),
        "port": sse_port,
        "ssePath": "/events"
    })
}

/// Create the SSE Reaction on the Drasi Server.
async fn create_reaction(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    reaction_id: &str,
    query_id: &str,
    sse_port: u16,
    sse_host: std::net::IpAddr,
) -> Result<(), String> {
    let url = reaction_api_url(server, instance, None)?;
    let body = reaction_config(reaction_id, query_id, sse_port, sse_host);

    let resp = client
        .post(url)
        .timeout(Duration::from_secs(30))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Failed to contact Drasi Server: {e}"))?;

    if resp.status().is_success() {
        Ok(())
    } else {
        Err(response_error(resp, "Failed to create reaction").await)
    }
}

/// Delete the SSE Reaction from the Drasi Server.
async fn delete_reaction(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    reaction_id: &str,
) -> Result<(), String> {
    let url = reaction_api_url(server, instance, Some(reaction_id))?;
    let resp = client
        .delete(url)
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .map_err(|error| format!("Failed to delete reaction '{reaction_id}': {error}"))?;
    if resp.status().is_success() {
        eprintln!("Reaction '{reaction_id}' deleted.");
        Ok(())
    } else {
        Err(response_error(resp, &format!("Failed to delete reaction '{reaction_id}'")).await)
    }
}

/// Preserve the endpoint's JSON payload, without interpreting row identities or changes.
fn handle_event(
    data: &str,
    debug: bool,
    output: &mut impl Write,
    log_file: &mut Option<impl Write>,
) -> Result<bool, String> {
    let value: serde_json::Value = serde_json::from_str(data)
        .map_err(|error| format!("Invalid JSON in SSE event: {error}"))?;
    if value.get("type").and_then(|value| value.as_str()) == Some("heartbeat") {
        let ts = value
            .get("ts")
            .and_then(|value| value.as_i64())
            .ok_or("Invalid SSE heartbeat: ts must be an integer timestamp")?;
        if debug {
            eprintln!("[heartbeat] ts={ts}");
        }
        return Ok(false);
    }
    let pretty = serde_json::to_string_pretty(&value)
        .map_err(|error| format!("Failed to format SSE JSON: {error}"))?;
    writeln!(output, "{pretty}")
        .and_then(|_| output.flush())
        .map_err(|error| format!("Failed to write stdout: {error}"))?;
    if let Some(file) = log_file.as_mut() {
        writeln!(file, "{pretty}")
            .and_then(|_| file.flush())
            .map_err(|error| format!("Failed to write event log: {error}"))?;
    }
    Ok(true)
}

/// Connect to the SSE endpoint and stream events until cancelled.
async fn stream_events(
    client: &reqwest::Client,
    sse_url: reqwest::Url,
    debug: bool,
    mut log_file: Option<std::fs::File>,
) -> Result<(), String> {
    let resp = tokio::time::timeout(
        Duration::from_secs(10),
        client
            .get(sse_url.clone())
            .header(reqwest::header::ACCEPT, "text/event-stream")
            .send(),
    )
    .await
    .map_err(|_| "Timed out connecting to SSE endpoint".to_string())?
    .map_err(|e| format!("Failed to connect to SSE endpoint: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status();
        return Err(format!("SSE endpoint returned {status}"));
    }
    let content_type = resp
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("");
    if !content_type
        .split(';')
        .next()
        .is_some_and(|value| value.trim().eq_ignore_ascii_case("text/event-stream"))
    {
        return Err(format!(
            "Expected text/event-stream, received '{content_type}'"
        ));
    }

    eprintln!("Connected to SSE stream at {sse_url}");

    let mut stream = resp.bytes_stream();
    let mut decoder = sse::Decoder::default();
    let mut output = std::io::stdout();

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("Stream error: {e}"))?;
        decoder.push(&chunk, debug, |data| {
            handle_event(data, debug, &mut output, &mut log_file).map(|_| ())
        })?;
    }
    decoder.finish()?;
    Err("SSE stream closed; notifications may have been missed. Reconnect explicitly and obtain a fresh snapshot if maintaining state.".into())
}

async fn run(args: Args) -> Result<(), String> {
    let log_file = args
        .log_file
        .as_ref()
        .map(|path| {
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .map_err(|error| format!("Could not open event log '{}': {error}", path.display()))
        })
        .transpose()?;
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .build()
        .map_err(|error| format!("Failed to create HTTP client: {error}"))?;

    if let Some(url) = args.sse_url {
        let url = http_url(&url)?;
        return until_interrupt(stream_events(&client, url, args.debug, log_file)).await;
    }
    let server = args.server.ok_or("A server URL is required")?;
    let instance = args.instance.ok_or("An instance ID is required")?;
    let query = args
        .query
        .filter(|value| !value.is_empty())
        .ok_or("A query ID is required")?;
    let reaction_id = format!("sse-cli-{}", uuid::Uuid::new_v4());
    reaction_api_url(&server, &instance, None)?;
    let sse_url = reaction_stream_url(&server, args.sse_port)?;

    // Create the SSE Reaction
    eprint!(
        "Creating SSE reaction '{reaction_id}' for query '{}'... ",
        query
    );
    if let Err(e) = create_reaction(
        &client,
        &server,
        &instance,
        &reaction_id,
        &query,
        args.sse_port,
        args.sse_host,
    )
    .await
    {
        return Err(format!(
            "{e}\nCreation was not confirmed. Check reaction '{reaction_id}' in instance '{instance}' if the server completed the request despite the error."
        ));
    }
    eprintln!("done.");
    eprintln!("Streaming events (Ctrl-C to stop)...\n");

    let result = until_interrupt(stream_events(&client, sse_url, args.debug, log_file)).await;
    let cleanup = delete_reaction(&client, &server, &instance, &reaction_id).await;
    match (result, cleanup) {
        (Err(error), Err(cleanup)) => Err(format!("{error}\nCleanup also failed: {cleanup}")),
        (Err(error), _) | (_, Err(error)) => Err(error),
        (Ok(()), Ok(())) => Ok(()),
    }
}

async fn until_interrupt(
    work: impl std::future::Future<Output = Result<(), String>>,
) -> Result<(), String> {
    tokio::select! {
        result = work => result,
        signal = tokio::signal::ctrl_c() => {
            signal.map_err(|error| format!("Could not listen for Ctrl-C: {error}"))?;
            eprintln!("\nShutting down...");
            Ok(())
        }
    }
}

#[tokio::main]
async fn main() -> std::process::ExitCode {
    match run(Args::parse()).await {
        Ok(()) => std::process::ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("Error: {error}");
            std::process::ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reaction_urls_require_and_encode_the_instance() {
        for instance in ["", ".", ".."] {
            assert!(reaction_api_url("http://localhost:8080", instance, None).is_err());
        }
        assert_eq!(
            reaction_api_url("http://localhost:8080/", "a/b %", Some("r?#"))
                .unwrap()
                .as_str(),
            "http://localhost:8080/api/v1/instances/a%2Fb%20%25/reactions/r%3F%23"
        );
        let args = Args::try_parse_from([
            "drasi-sse-cli",
            "--server",
            "http://localhost:8080",
            "--instance",
            "selected",
            "--query",
            "q",
        ])
        .unwrap();
        assert_eq!(args.instance.as_deref(), Some("selected"));
    }

    #[test]
    fn existing_endpoint_mode_is_explicit_and_exclusive() {
        let direct = ["drasi-sse-cli", "--sse-url", "http://localhost:9010/events"];
        assert!(Args::try_parse_from(direct).is_ok());
        for extra in [
            ["--server", "http://localhost:8080"],
            ["--instance", "selected"],
            ["--query", "q"],
            ["--sse-port", "8091"],
            ["--sse-host", "0.0.0.0"],
        ] {
            assert!(Args::try_parse_from(direct.into_iter().chain(extra)).is_err());
        }
        assert!(Args::try_parse_from(["drasi-sse-cli"]).is_err());
        assert!(Args::try_parse_from([
            "drasi-sse-cli",
            "-s",
            "http://localhost:8080",
            "-i",
            "selected",
            "-q",
            "q",
            "-p",
            "0",
        ])
        .is_err());
    }

    #[test]
    fn reaction_defaults_to_loopback_and_remote_binding_requires_opt_in() {
        let command = [
            "drasi-sse-cli",
            "-s",
            "http://localhost:8080",
            "-i",
            "selected",
            "-q",
            "q",
        ];
        let args = Args::try_parse_from(command).unwrap();
        assert_eq!(
            reaction_config("r", "q", args.sse_port, args.sse_host),
            serde_json::json!({
                "kind": "sse", "id": "r", "queries": ["q"], "autoStart": true,
                "host": "127.0.0.1", "port": 8090, "ssePath": "/events"
            })
        );
        let remote =
            Args::try_parse_from(command.into_iter().chain(["--sse-host", "0.0.0.0"])).unwrap();
        assert_eq!(
            reaction_config("r", "q", remote.sse_port, remote.sse_host)["host"],
            "0.0.0.0"
        );
        assert_eq!(
            reaction_stream_url("https://server.example/api-prefix", 9090)
                .unwrap()
                .as_str(),
            "http://server.example:9090/events"
        );
        assert_eq!(
            reaction_stream_url("http://[::1]:8080", 9090)
                .unwrap()
                .as_str(),
            "http://[::1]:9090/events"
        );
        for value in [
            "file:///tmp/events",
            "ftp://example.com",
            "http://host/#fragment",
        ] {
            assert!(http_url(value).is_err());
        }
        assert!(reaction_api_url("http://host/?query=1", "i", None).is_err());
    }

    fn printed(data: &str) -> String {
        let mut output = Vec::new();
        let mut log = Some(Vec::new());
        assert!(handle_event(data, false, &mut output, &mut log).unwrap());
        assert_eq!(output, log.unwrap());
        String::from_utf8(output).unwrap()
    }

    #[test]
    fn preserves_adapter_diff_variants_and_full_width_signatures() {
        let value = serde_json::json!({
            "queryId": "q",
            "timestamp": 123,
            "results": [
                {"type": "ADD", "data": {"name": "before"}, "row_signature": u64::MAX},
                {"type": "UPDATE", "data": {"name": "after"},
                 "before": {"name": "before"}, "after": {"name": "after"},
                 "row_signature": u64::MAX, "grouping_keys": ["name"]},
                {"type": "DELETE", "data": {"name": "after"}, "row_signature": u64::MAX},
                {"type": "aggregation", "before": null, "after": {"count": 2}, "row_signature": 3},
                {"type": "noop"}
            ]
        });
        let actual: serde_json::Value = serde_json::from_str(&printed(&value.to_string())).unwrap();
        assert_eq!(actual, value);
        assert!(!actual["results"][0].as_object().unwrap().contains_key("op"));
    }

    #[test]
    fn preserves_native_patch_removals_identity_only_delete_and_rich_values() {
        let payload = r#"{
            "output": {"alias":"items","component":"source","port":"out"},
            "sequence": 18446744073709551615,
            "publishedAt": 123,
            "changes": [
                {"operation":"ADD","identity":{"namespace":"inventory","id":"one"},
                 "element":{"kind":"node","labels":["Item"]},
                 "after":{"nested":[null,true,{"large":18446744073709551615}],
                          "date":"2026-10-27","duration":"PT5S"}},
                {"operation":"REPLACE","identity":{"namespace":"inventory","id":"one"},"after":{"name":"café"}},
                {"operation":"PATCH","identity":{"namespace":"inventory","id":"one"},
                 "after":{"name":null},"removedProperties":["old"],"effectiveFrom":123},
                {"operation":"DELETE","identity":{"namespace":"inventory","id":"one"}}
            ],
            "extensionNumber": 123456789012345678901234567890.123456789
        }"#;
        let output = printed(payload);
        let actual: serde_json::Value = serde_json::from_str(&output).unwrap();
        assert_eq!(
            actual,
            serde_json::from_str::<serde_json::Value>(payload).unwrap()
        );
        assert!(output.contains("123456789012345678901234567890.123456789"));
        assert!(actual.get("queryId").is_none());
        for change in actual["changes"].as_array().unwrap() {
            assert!(change.get("before").is_none());
            assert!(change.get("row_signature").is_none());
        }
        assert!(actual["changes"][3].get("after").is_none());
        assert!(actual["changes"][3].get("data").is_none());
    }

    #[test]
    fn preserves_api_snapshot_arrays_and_query_result_payload_without_relabeling() {
        for data in [
            r#"[{"count":1}]"#,
            r#"{"query_id":"q","sequence":1,"timestamp":"2026-10-27T00:00:00Z","metadata":{},"results":[]}"#,
        ] {
            assert_eq!(
                serde_json::from_str::<serde_json::Value>(&printed(data)).unwrap(),
                serde_json::from_str::<serde_json::Value>(data).unwrap()
            );
        }
    }

    #[test]
    fn ignores_only_valid_heartbeats_and_reports_malformed_data() {
        let mut output = Vec::new();
        let mut log = Some(Vec::new());
        assert!(!handle_event(
            r#"{"type":"heartbeat","ts":123}"#,
            false,
            &mut output,
            &mut log
        )
        .unwrap());
        assert!(output.is_empty());
        assert!(log.as_ref().unwrap().is_empty());
        for data in [
            "not json",
            r#"{"type":"heartbeat"}"#,
            r#"{"type":"heartbeat","ts":"bad"}"#,
        ] {
            assert!(handle_event(data, false, &mut output, &mut log).is_err());
        }
    }

    struct BrokenWriter;

    impl Write for BrokenWriter {
        fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
            Err(std::io::Error::other("intentional write failure"))
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Err(std::io::Error::other("intentional flush failure"))
        }
    }

    #[test]
    fn reports_stdout_and_log_write_failures() {
        assert!(
            handle_event("{}", false, &mut BrokenWriter, &mut None::<Vec<u8>>)
                .unwrap_err()
                .contains("stdout")
        );
        assert!(
            handle_event("{}", false, &mut Vec::new(), &mut Some(BrokenWriter))
                .unwrap_err()
                .contains("event log")
        );
    }
}
