Background:
    - We are working on a project called Drasi.
    - Drasi is a Data Change Processing platform that detects and reacts to changes in data.
    - Drasi Server is a single self-contained server (a native binary) that runs Drasi. It is configured with a YAML config file and managed through a REST API. It does NOT use Kubernetes or a separate Drasi CLI.
    - For completely new users, we've written a Getting Started tutorial.
    - The tutorial is for complete beginners to Drasi Server, to try it hands-on.

Environment:
    - You are already placed inside the devcontainer environment described in the tutorial's "Dev Container" setup option.
    - The devcontainer has already completed Step 1 (Set Up Your Environment) for you:
        ○ The Drasi Server binary is available at `./bin/drasi-server`.
        ○ The Drasi SSE CLI binary is available at `./bin/drasi-sse-cli`.
        ○ The PostgreSQL client (`psql`), `docker`, and `curl` are installed and on the PATH.
    - Because you are running inside the devcontainer, you do NOT need to set up any port forwarding. `localhost` works directly.
    - PostgreSQL is reached by Drasi Server at `getting-started-postgres:5432` on the shared Docker network (`DB_HOST` is already set). The devcontainer publishes PostgreSQL on host port 5532, so `5532->5432` in `docker compose ps` is expected. This does not change the Source port inside the Docker network.
    - The current working directory is the repository root.
    - In scheduled evaluations, this may be an isolated copy of the tutorial workspace for the current attempt; all tutorial-relative paths remain the same.

Non-interactive terminal:
    - There is no TTY in the evaluator shell. For tutorial commands using `docker exec -it`, use `docker exec -i` instead, leaving the rest of the command unchanged. This only disables pseudo-terminal allocation; it does not change the database operation.
    - Do not treat the absence of a TTY as a tutorial failure or introduce an interactive terminal workaround.

Tutorial Docs:
    - Follow the tutorial documentation at @tutorial-docs/README.md .
    - This tutorial is driven entirely through the terminal. There are no screenshots or web pages to compare against.
    - At the end of the tutorial you must write a final markdown report indicating success or failure. This should reflect whether a new human user can follow the instructions without getting confused.

Goal:
    - You are an agent that will act like a new human user to Drasi Server and follow the tutorial step by step.
    - At each step, evaluate whether the instructions or the expected output (or effect or change) described in the tutorial are ambiguous for you (or a human).
    - After each step, compare the output you actually see with the expected output described in the tutorial.
    - Write a final report that includes a success/fail metric indicating whether you were able to follow through all the steps in the tutorial successfully.

Where to start:
    - Step 1 of the tutorial ("Set Up Your Environment") has already been completed by the devcontainer, so you do NOT need to choose or perform a setup option (Download Binary / Codespace / Dev Container / Build from Source). Treat the environment as the "Dev Container" path already done.
    - Begin your evaluation at "Step 2 of 7: Set Up the Tutorial Database" and continue through the end of the tutorial.
    - As a quick sanity check before Step 2, you may run `./bin/drasi-server --version` and `./bin/drasi-sse-cli --version` and capture the output. If either binary is missing, terminate the evaluation immediately and mark it as failed.

Running long-lived processes (IMPORTANT):
    - The tutorial uses multiple terminals: Terminal 1 runs Drasi Server, Terminal 2 runs `docker` / `curl` / `psql` commands, and Terminal 3 runs the SSE CLI.
    - You only have a single shell, so emulate the multiple terminals by running the long-lived processes in the background and redirecting their output to files inside your evaluation directory, then inspecting those files.
    - For the Drasi Server process (Terminal 1): start it in the background with its output redirected to a log file (for example `nohup ./bin/drasi-server --config getting-started.yaml > evaluation-<timestamp>/NN_drasi-server.log 2>&1 &`). Wait a few seconds, then read the log file to confirm it started and reported the API address before continuing. The Log Reaction output that the tutorial asks you to observe will appear in this log file.
    - For the SSE CLI process (Terminal 3): start it in the background the same way, redirecting to its own log file, then read that file to observe streamed events.
    - Give background processes a short, bounded wait (a few seconds) before reading their output so events have time to arrive. Do not wait indefinitely.
    - For time-based tutorial steps, follow the guide's explicit 20-second waits instead of the short startup wait. Apart from the Step 6 initialization timing allowance below, do not add undocumented setup steps or change the expected transitions to make an evaluation pass.
    - Keep track of the background process IDs and ensure you read from the correct log file when verifying each step's expected output.
    - When the tutorial says to press Ctrl+C, send SIGINT only to the recorded SSE CLI process ID. Do not use process-name matching that could also stop the server or evaluator.

Evaluation Criteria:
    - For CLI / REST output, the output may not match exactly character by character. Ignore whitespace and fields like timestamps or GUIDs that change between runs. But core data and status fields must match the expectation (for example a Source name and its status, query result rows, sender names, and aggregation counts).
    - Field ordering may differ, ID fields may be represented as numbers or strings, and additional metadata fields (such as `row_signature` on aggregation events) may be present — the tutorial itself notes this, so treat those as acceptable variations.
    - Tutorial instructions must be unambiguous for any agent or human.
    - The sequence of instructions must be unambiguous for any agent or human.
    - The tutorial instructions should not contain assumptions that are not expressed clearly.

Step 6 initialization timing allowance:
    - The PostgreSQL bootstrap timestamps existing rows when the new query loads them. The `inactive-senders` result set can therefore be empty initially, even though the guide describes it as immediately populated.
    - After successfully creating `inactive-senders`, record the time and start the SSE CLI as instructed. Before inserting Alice's next message, allow up to 30 seconds from query creation for the existing senders to become inactive. You may use bounded sleeps and repeat `GET http://localhost:8080/api/v1/queries/inactive-senders/results` every 2 seconds within that deadline.
    - Verify a successful API response whose `data` array contains the expected senders: Buzz Lightyear, Brian Kernighan, Antoninus, David, Alice, and Bob. Proceed as soon as that state is present; do not require a fresh initial SSE notification if it was emitted before the CLI connected.
    - Fail if the expected state is still absent at the 30-second deadline. API errors, invalid responses, server exits, and SSE connection failures remain failures; this allowance only tolerates a temporarily incomplete initial result set.
    - Once the initial state is verified, follow the guide's Alice inserts and 20-second waits unchanged. Verify the documented DELETE/ADD transitions; do not skip them or change the query, data, or configuration to force success.
    - Record the initial results, elapsed wait, and final results in the evaluation evidence. Note delayed population as a non-blocking documentation timing discrepancy in the report, rather than claiming that the guide's immediate-population statement matched. This allowance does not waive any other failure.

Output Details:
    - All output must go into a folder named `evaluation-` suffixed with the timestamp of the start of this run. Create this folder at the very start.
    - Output of any CLI / REST command that is considered during evaluation must be copied to a text file. These files must have a two digit number and an underscore as a prefix in their name, incrementing to preserve order — for example `01_db-sample-data.txt`, `02_drasi-server.log`, `03_create-query.txt`.
    - A single final file `report.md` must be generated at the end in the evaluation directory.
        ○ CRITICAL: The STATUS line must appear EXACTLY ONCE in the entire report. Write `## STATUS: SUCCESS` or `## STATUS: FAILURE` only at the END of the report, NEVER per step.
        ○ Do NOT write "STATUS: SUCCESS" or "STATUS: FAILURE" for individual steps. Use other words like "Step passed", "Step failed", "Verified", etc. for per-step results.
        ○ The rest of the file can explain why the tutorial passed or failed evaluation.
        ○ For each step of the tutorial you follow and evaluate, add a section to this markdown file.
        ○ You can reference the text files / log files you captured for evaluation.

Skip Directives:
    - Some tutorial sections may be marked optional and should be skipped during evaluation.
    - Format: `<!-- drasi-eval-skip-start id="<id>" reason="<reason>" -->` ... `<!-- drasi-eval-skip-end id="<id>" -->`
    - Skip all content between matching start/end markers. Do not execute commands or verify outputs within.
    - In your report, list each skipped section by id and include the reason verbatim.

Constraints:
    - You must run only the commands explicitly specified in the tutorial doc (plus the version sanity check, the non-TTY adaptation, the process-management/redirection mechanics, and the bounded Step 6 initialization checks described above).
    - You must NOT set up any extra port forwarding — everything is already set up in the devcontainer. If something networking-related is not working, terminate the evaluation immediately and mark it as failed.
    - If something is broken, terminate the evaluation immediately and mark it as failed.
    - If any instruction is unclear or ambiguous, terminate the evaluation immediately and mark it as failed, except for the explicitly permitted Step 6 initialization timing allowance.
    - If you hit a mismatch between expected output / behavior and what you observe, terminate the evaluation immediately and mark it as failed, except for the explicitly permitted Step 6 initialization timing allowance.
    - You must NOT debug failures or fix anything. Upon hitting any failure, terminate the evaluation immediately and mark it as failed.
    - Do not perform any cleanup steps (stopping the server, `docker compose down`, etc.) that the tutorial lists at the end, even if mentioned in the docs.
    - Whatever scripts you write or files you create must remain within the evaluation directory you create at the start of the task.

Final Checklist (complete these before ending):
    1. Ensure `report.md` exists in the evaluation directory.
    2. Verify that `report.md` ends with EXACTLY ONE line: `## STATUS: SUCCESS` or `## STATUS: FAILURE`.
    3. Verify you have NOT written "STATUS: SUCCESS" or "STATUS: FAILURE" anywhere else in the report.
