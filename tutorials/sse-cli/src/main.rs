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

    /// Exact query name to resolve once, even when it looks like a UUID
    #[arg(short, long, env = "DRASI_QUERY", required_unless_present_any = ["sse_url", "query_id"], conflicts_with = "query_id")]
    query: Option<String>,

    /// Existing query UUID, instead of resolving a name
    #[arg(long, env = "DRASI_QUERY_ID", conflicts_with = "query")]
    query_id: Option<uuid::Uuid>,

    /// Observe an existing SSE endpoint without creating or deleting a reaction
    #[arg(long, conflicts_with_all = ["server", "instance", "query", "query_id", "sse_port", "sse_host"])]
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

fn instance_api_url(
    server: &str,
    instance: &str,
    segments: &[&str],
) -> Result<reqwest::Url, String> {
    if instance.is_empty()
        || matches!(instance, "." | "..")
        || segments
            .iter()
            .any(|segment| segment.is_empty() || matches!(*segment, "." | ".."))
    {
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
            .extend(["api", "v1", "instances", instance])
            .extend(segments);
    }
    Ok(url)
}

fn reaction_api_url(
    server: &str,
    instance: &str,
    reaction: Option<&str>,
) -> Result<reqwest::Url, String> {
    match reaction {
        Some(id) => instance_api_url(server, instance, &["reactions", id]),
        None => instance_api_url(server, instance, &["reactions"]),
    }
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
    reaction_name: &str,
    query_id: &str,
    sse_port: u16,
    sse_host: std::net::IpAddr,
) -> serde_json::Value {
    serde_json::json!({
        "kind": "sse",
        "name": reaction_name,
        "queries": [{"id": query_id}],
        "autoStart": true,
        "host": sse_host.to_string(),
        "port": sse_port,
        "ssePath": "/events"
    })
}

#[derive(serde::Deserialize)]
struct ApiResponse<T> {
    success: bool,
    data: Option<T>,
}

#[derive(serde::Deserialize)]
struct AssignedComponent {
    id: String,
    name: String,
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct ConfigurationReceipt {
    request_id: String,
    components: Vec<AssignedComponent>,
}

#[derive(serde::Deserialize)]
struct ConfigurationRevision {
    revision: u64,
}

async fn api_request<T: serde::de::DeserializeOwned>(
    request: reqwest::RequestBuilder,
    operation: &str,
) -> Result<T, String> {
    let response = request
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .map_err(|error| format!("{operation}: {error}"))?;
    if !response.status().is_success() {
        return Err(response_error(response, operation).await);
    }
    let response: ApiResponse<T> = response
        .json()
        .await
        .map_err(|error| format!("{operation}: invalid API response: {error}"))?;
    if !response.success {
        return Err(format!("{operation}: server did not confirm success"));
    }
    response
        .data
        .ok_or_else(|| format!("{operation}: server omitted response data"))
}

async fn query_identity(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    name: Option<&str>,
    id: Option<uuid::Uuid>,
) -> Result<String, String> {
    let id = match id {
        Some(id) => id.to_string(),
        None => {
            let name = name
                .filter(|name| !name.is_empty())
                .ok_or("A query name or UUID is required")?;
            let component: AssignedComponent = api_request(
                client.get(instance_api_url(
                    server,
                    instance,
                    &["components", "by-name", name],
                )?),
                "Could not resolve query name",
            )
            .await?;
            if component.name != name {
                return Err("Name lookup returned a different component name".into());
            }
            component.id
        }
    };
    let canonical = uuid::Uuid::parse_str(&id)
        .map_err(|error| format!("Invalid query UUID: {error}"))?
        .to_string();
    if canonical != id {
        return Err("Server returned a noncanonical query UUID".into());
    }
    let status: serde_json::Value = api_request(
        client.get(instance_api_url(server, instance, &["queries", &id])?),
        "Could not inspect query",
    )
    .await?;
    if status["id"] != id || status["status"] != "Running" {
        return Err(format!("Query '{id}' is not running: {}", status["status"]));
    }
    Ok(id)
}

async fn revision(client: &reqwest::Client, server: &str, instance: &str) -> Result<u64, String> {
    let configuration: ConfigurationRevision = api_request(
        client.get(instance_api_url(
            server,
            instance,
            &["computation", "desired"],
        )?),
        "Could not read configuration revision",
    )
    .await?;
    Ok(configuration.revision)
}

/// Create the SSE Reaction on the Drasi Server.
async fn create_reaction(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    definition: &serde_json::Value,
    request_id: &str,
) -> Result<String, String> {
    let receipt: ConfigurationReceipt = api_request(
        client
            .post(instance_api_url(
                server,
                instance,
                &["computation", "ordinary-definitions"],
            )?)
            .json(&serde_json::json!({
                "expectedRevision": revision(client, server, instance).await?,
                "requestId": request_id,
                "component": {"type": "reaction", "definition": definition}
            })),
        "Could not create reaction",
    )
    .await?;
    if receipt.request_id != request_id
        || receipt.components.len() != 1
        || definition["name"] != receipt.components[0].name
    {
        return Err("Creation receipt did not confirm the requested reaction".into());
    }
    let id = &receipt.components[0].id;
    let canonical = uuid::Uuid::parse_str(id)
        .map_err(|error| format!("Invalid assigned UUID: {error}"))?
        .to_string();
    if canonical != *id {
        return Err("Creation receipt returned a noncanonical UUID".into());
    }
    Ok(canonical)
}

/// Delete the SSE Reaction from the Drasi Server.
async fn delete_reaction(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    reaction_id: &str,
) -> Result<(), String> {
    let request_id = uuid::Uuid::new_v4().to_string();
    let receipt: ConfigurationReceipt = api_request(
        client
            .delete(instance_api_url(
                server,
                instance,
                &["computation", "ordinary-definitions", reaction_id],
            )?)
            .json(&serde_json::json!({
                "expectedRevision": revision(client, server, instance).await?,
                "requestId": request_id,
            })),
        &format!("Could not delete reaction '{reaction_id}'"),
    )
    .await?;
    if receipt.request_id != request_id || !receipt.components.is_empty() {
        return Err("Removal receipt did not confirm the requested operation".into());
    }
    eprintln!("Removal accepted for reaction '{reaction_id}'.");
    Ok(())
}

async fn wait_for_reaction(
    client: &reqwest::Client,
    server: &str,
    instance: &str,
    id: &str,
) -> Result<(), String> {
    let url = reaction_api_url(server, instance, Some(id))?;
    tokio::time::timeout(Duration::from_secs(30), async {
        loop {
            let component: serde_json::Value =
                api_request(client.get(url.clone()), "Could not inspect reaction").await?;
            if component["id"] != id {
                return Err("Reaction inspection returned a different UUID".into());
            }
            match component["status"].as_str() {
                Some("Running") => return Ok(()),
                Some("Added" | "Starting" | "Stopped" | "Reconfiguring") => {
                    tokio::time::sleep(Duration::from_millis(100)).await;
                }
                status => {
                    return Err(format!(
                        "Reaction '{id}' cannot start: {status:?}; {}",
                        component["errorMessage"]
                    ))
                }
            }
        }
    })
    .await
    .map_err(|_| format!("Timed out waiting for reaction '{id}' to start"))?
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
    let query = query_identity(
        &client,
        &server,
        &instance,
        args.query.as_deref(),
        args.query_id,
    )
    .await?;
    let request_id = uuid::Uuid::new_v4().to_string();
    let reaction_name = format!("sse-cli-{request_id}");
    reaction_api_url(&server, &instance, None)?;
    let sse_url = reaction_stream_url(&server, args.sse_port)?;

    // Create the SSE Reaction
    eprint!(
        "Creating SSE reaction '{reaction_name}' for query '{}'... ",
        query
    );
    let definition = reaction_config(&reaction_name, &query, args.sse_port, args.sse_host);
    let reaction_id = create_reaction(
        &client,
        &server,
        &instance,
        &definition,
        &request_id,
    ).await.map_err(|error| format!(
        "{error}\nCreation was not confirmed. Inspect request receipt '{request_id}' in instance '{instance}' before retrying; the reaction name is '{reaction_name}'."
    ))?;
    eprintln!("done.");
    eprintln!("Streaming events (Ctrl-C to stop)...\n");

    let result = until_interrupt(async {
        wait_for_reaction(&client, &server, &instance, &reaction_id).await?;
        stream_events(&client, sse_url, args.debug, log_file).await
    })
    .await;
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

    const QUERY_ID: &str = "08f93596-5c0d-4c5d-890a-cf015bb3d809";
    const REACTION_ID: &str = "32408b47-4678-45b1-b77d-917519d6fdb4";

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
            ["--query-id", QUERY_ID],
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
            reaction_config("r", QUERY_ID, args.sse_port, args.sse_host),
            serde_json::json!({
                "kind": "sse", "name": "r", "queries": [{"id": QUERY_ID}], "autoStart": true,
                "host": "127.0.0.1", "port": 8090, "ssePath": "/events"
            })
        );
        let remote =
            Args::try_parse_from(command.into_iter().chain(["--sse-host", "0.0.0.0"])).unwrap();
        assert_eq!(
            reaction_config("r", QUERY_ID, remote.sse_port, remote.sse_host)["host"],
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

    #[test]
    fn query_uuid_is_an_explicit_selector_not_a_name_guess() {
        let command = [
            "drasi-sse-cli",
            "--server",
            "http://localhost:8080",
            "--instance",
            "selected",
        ];
        let named = Args::try_parse_from(command.into_iter().chain(["--query", QUERY_ID])).unwrap();
        assert_eq!(named.query.as_deref(), Some(QUERY_ID));
        assert!(named.query_id.is_none());
        let identified =
            Args::try_parse_from(command.into_iter().chain(["--query-id", QUERY_ID])).unwrap();
        assert_eq!(identified.query_id.unwrap().to_string(), QUERY_ID);
        assert!(identified.query.is_none());
        assert!(
            Args::try_parse_from(command.into_iter().chain(["--query-id", "query-name"])).is_err()
        );
        assert!(Args::try_parse_from(command.into_iter().chain([
            "--query",
            "q",
            "--query-id",
            QUERY_ID
        ]))
        .is_err());
    }

    async fn mock_api(
        responses: Vec<serde_json::Value>,
    ) -> (
        String,
        tokio::task::JoinHandle<Vec<(String, serde_json::Value)>>,
    ) {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move {
            let mut requests = Vec::new();
            for mut data in responses {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut bytes = Vec::new();
                let end = loop {
                    if let Some(position) = bytes.windows(4).position(|part| part == b"\r\n\r\n") {
                        break position + 4;
                    }
                    let mut buffer = [0; 1024];
                    let count = socket.read(&mut buffer).await.unwrap();
                    assert!(count > 0 && bytes.len() < 65_536);
                    bytes.extend_from_slice(&buffer[..count]);
                };
                let headers = String::from_utf8(bytes[..end].to_vec()).unwrap();
                let length = headers
                    .lines()
                    .filter_map(|line| line.split_once(':'))
                    .find(|(name, _)| name.eq_ignore_ascii_case("content-length"))
                    .map(|(_, length)| length.trim().parse::<usize>().unwrap())
                    .unwrap_or(0);
                while bytes.len() - end < length {
                    let mut buffer = [0; 1024];
                    let count = socket.read(&mut buffer).await.unwrap();
                    assert!(count > 0);
                    bytes.extend_from_slice(&buffer[..count]);
                }
                let body = if length == 0 {
                    serde_json::Value::Null
                } else {
                    serde_json::from_slice(&bytes[end..end + length]).unwrap()
                };
                if data["requestId"] == "$requestId" {
                    data["requestId"] = body["requestId"].clone();
                }
                requests.push((headers.lines().next().unwrap().to_string(), body));
                let response = serde_json::json!({"success": true, "data": data}).to_string();
                socket.write_all(format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                    response.len(), response,
                ).as_bytes()).await.unwrap();
            }
            requests
        });
        (address, server)
    }

    #[tokio::test]
    async fn name_lookup_binds_once_to_returned_uuid() {
        let (address, server) = mock_api(vec![
            serde_json::json!({"id": REACTION_ID, "name": QUERY_ID}),
            serde_json::json!({"id": REACTION_ID, "name": "renamed", "status": "Running"}),
        ])
        .await;
        let id = query_identity(
            &reqwest::Client::new(),
            &address,
            "selected",
            Some(QUERY_ID),
            None,
        )
        .await
        .unwrap();
        assert_eq!(id, REACTION_ID);
        let requests = server.await.unwrap();
        assert_eq!(
            requests[0].0,
            format!("GET /api/v1/instances/selected/components/by-name/{QUERY_ID} HTTP/1.1")
        );
        assert_eq!(
            requests[1].0,
            format!("GET /api/v1/instances/selected/queries/{REACTION_ID} HTTP/1.1")
        );
    }

    #[tokio::test]
    async fn explicit_uuid_does_not_perform_name_lookup() {
        let (address, server) = mock_api(vec![
            serde_json::json!({"id": QUERY_ID, "name": "q", "status": "Running"}),
        ])
        .await;
        assert_eq!(
            query_identity(
                &reqwest::Client::new(),
                &address,
                "selected",
                None,
                Some(uuid::Uuid::parse_str(QUERY_ID).unwrap())
            )
            .await
            .unwrap(),
            QUERY_ID
        );
        let requests = server.await.unwrap();
        assert_eq!(
            requests[0].0,
            format!("GET /api/v1/instances/selected/queries/{QUERY_ID} HTTP/1.1")
        );
    }

    #[tokio::test]
    async fn revisioned_creation_waits_for_and_removes_only_the_assigned_reaction() {
        let (address, server) = mock_api(vec![
            serde_json::json!({"revision": 4}),
            serde_json::json!({"requestId": "create", "components": [{"id": REACTION_ID, "name": "temporary"}]}),
            serde_json::json!({"id": REACTION_ID, "status": "Starting"}),
            serde_json::json!({"id": REACTION_ID, "status": "Running"}),
            serde_json::json!({"revision": 5}),
            serde_json::json!({"requestId": "$requestId", "components": []}),
        ]).await;
        let client = reqwest::Client::new();
        let definition = reaction_config("temporary", QUERY_ID, 8090, "127.0.0.1".parse().unwrap());
        let assigned = create_reaction(&client, &address, "selected", &definition, "create")
            .await
            .unwrap();
        assert_eq!(assigned, REACTION_ID);
        wait_for_reaction(&client, &address, "selected", &assigned)
            .await
            .unwrap();
        delete_reaction(&client, &address, "selected", &assigned)
            .await
            .unwrap();
        let requests = server.await.unwrap();
        assert_eq!(
            requests[1].0,
            "POST /api/v1/instances/selected/computation/ordinary-definitions HTTP/1.1"
        );
        assert_eq!(
            requests[1].1,
            serde_json::json!({
                "expectedRevision": 4, "requestId": "create",
                "component": {"type": "reaction", "definition": definition}
            })
        );
        assert!(requests[1].1["component"]["definition"].get("id").is_none());
        assert_eq!(requests[5].0, format!("DELETE /api/v1/instances/selected/computation/ordinary-definitions/{REACTION_ID} HTTP/1.1"));
        assert_eq!(requests[5].1["expectedRevision"], 5);
        assert!(uuid::Uuid::parse_str(requests[5].1["requestId"].as_str().unwrap()).is_ok());
    }

    #[tokio::test]
    async fn invalid_creation_receipts_never_confirm_ownership() {
        for (request, components) in [
            (
                "different-request",
                serde_json::json!([{"id": REACTION_ID, "name": "temporary"}]),
            ),
            ("create", serde_json::json!([])),
            (
                "create",
                serde_json::json!([{"id": REACTION_ID, "name": "someone-else"}]),
            ),
            (
                "create",
                serde_json::json!([{"id": "temporary", "name": "temporary"}]),
            ),
            (
                "create",
                serde_json::json!([{"id": REACTION_ID.to_uppercase(), "name": "temporary"}]),
            ),
        ] {
            let (address, server) = mock_api(vec![
                serde_json::json!({"revision": 4}),
                serde_json::json!({"requestId": request, "components": components}),
            ])
            .await;
            let definition =
                reaction_config("temporary", QUERY_ID, 8090, "127.0.0.1".parse().unwrap());
            assert!(create_reaction(
                &reqwest::Client::new(),
                &address,
                "selected",
                &definition,
                "create"
            )
            .await
            .is_err());
            assert_eq!(server.await.unwrap().len(), 2);
        }
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
