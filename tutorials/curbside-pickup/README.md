<!-- DO NOT EDIT. Generated from _index.md by scripts/render-tutorials.py. Edit _index.md and run `python3 scripts/render-tutorials.py`. -->

Imagine a store running curbside pickup. The **retail team** manages customer orders in one database and marks an order *ready* when it's prepared. Independently, the **physical operations team** tracks pickup vehicles in *another* database, and a driver sets their location to *Curbside* when they arrive. The two systems never talk to each other.

You want a single live dashboard with six panels:

- an **Orders · Preparing** panel and an **Orders · Ready** panel, so an order visibly moves from one to the other the moment it's marked *ready*,
- a **Vehicles · Parking** panel and a **Vehicles · Curbside** panel, so a car moves between them as the driver pulls up, plus the two situations that matter:
- a **Matched Orders** panel that lights up the instant an order is *ready* **and** its driver is at the curbside, so staff know exactly which order to carry out, and
- a **Delayed Orders** panel that flags drivers who have been waiting at the curbside too long while their order still isn't ready.

The catch: the orders live in **PostgreSQL** and the vehicles live in **MySQL**. Building this the traditional way means CDC pipelines, a stream processor, a websocket backend, and a custom front end. This tutorial builds it on **Drasi Server** instead: two sources, six continuous queries (two of which join across both databases), and the built-in **dashboard reaction** - **no application code and no bespoke web UI**. A small **operations console** - available as both a terminal app and a browser page - stands in for the two operations teams so you can drive the changes yourself and watch every SQL statement as it runs.

**Sources** → **Continuous Queries** → **Reactions**

- **Sources** — Connect to your data sources
- **Continuous Queries** — Define what changes matter
- **Reactions** — Take action automatically

| Step | What You'll Do |
| ---- | ------------- |
| **[Step 1: Set Up Your Environment](#step-1-of-4-set-up-your-environment)** | Open the dev container (or install the tools locally) |
| **[Step 2: Run the Demo](#step-2-of-4-run-the-demo)** | One command starts both databases and Drasi Server |
| **[Step 3: Open the Dashboard](#step-3-of-4-open-the-dashboard)** | Watch all six panels update live |
| **[Step 4: Drive Change](#step-4-of-4-drive-change)** | Use the terminal or browser console to change orders and vehicles, and watch Drasi react |
| **[How It Works](#how-it-works)** | Understand the two sources, the cross-database join, and the six queries |

> **Before you begin**
>
> - **Terminals:** you'll use two. **Terminal 1** runs the demo (it stays in the foreground). **Terminal 2** runs the operations console you drive changes from.
> - **Working directory:** run every command from the tutorial directory (`tutorials/curbside-pickup/`). The dev container opens there automatically; if you're running locally, `cd tutorials/curbside-pickup` first.
> - **Command tabs:** commands are shown in tabs (*bash / zsh* and *PowerShell*). Use the one for your shell. The dev container and Codespaces use *bash*.
> - **Ports:** the Drasi Server API is on `8480`, the dashboard is on `3000`, the (optional) browser console is on `3001`, PostgreSQL is published on `5742`, and MySQL on `3309`.

## Step 1 of 4: Set Up Your Environment
This tutorial needs **Docker** (it runs PostgreSQL and MySQL) and **Node.js 18+** (for the operations console). The easiest way to get everything is the **dev container**.

### Option A: Dev Container or GitHub Codespaces (recommended)

1. Open this repository in VS Code and run **Reopen in Container** (or create a **Codespace** from the repo's **Code** menu).
2. When prompted for a configuration, choose **Drasi Server - Curbside Pickup Tutorial**.
3. Wait for the container to finish. Its setup script downloads the Drasi Server binary and installs the console's dependencies.

That's it. Skip ahead to [Step 2](#step-2-of-4-run-the-demo).

### Option B: Run Locally

You'll need **Docker**, **Node.js 18+**, and **bash** (the helper scripts use it; on Windows use Git Bash or WSL, or use the PowerShell tabs). From the repository root, move into the tutorial directory and download the Drasi Server binary:

**bash / zsh**

```bash
cd tutorials/curbside-pickup
bash scripts/download.sh
```

**PowerShell**

```powershell
cd tutorials/curbside-pickup
powershell -ExecutionPolicy Bypass -File scripts/download.ps1
```

This places the binary at `bin/drasi-server` (or `bin\drasi-server.exe` on Windows) inside the tutorial directory.

## Step 2 of 4: Run the Demo
Everything runs from a single configuration file, `server-config.yaml`. In **Terminal 1**, start the demo:

**bash / zsh**

```bash
bash scripts/start-demo.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-demo.ps1
```

The `start-demo` script does two things:

1. **Starts the databases.** PostgreSQL comes up with logical replication enabled and the `orders` table seeded (three orders, all *preparing*). MySQL comes up with **ROW-based binary logging** (and GTID mode) enabled on the `vehicles` table (three vehicles, all *Parking*) - the plates match the orders.
2. **Runs Drasi Server** in the foreground with the full configuration.

On first start, Drasi Server downloads the plugins it needs (`source/postgres`, `bootstrap/postgres`, `source/mysql`, `bootstrap/mysql`, `reaction/dashboard`) from `ghcr.io/drasi-project` and caches them under `~/.drasi/plugins`, connects to both databases, bootstraps the existing rows, starts the six continuous queries, and starts the dashboard. When you see a line like the following, it's ready:

```text
Drasi Server started successfully with API on port 8480
```

Leave this running. Everything else happens from **Terminal 2** (or your browser).

> **Stopping and resetting**
>
> Press **Ctrl+C** in Terminal 1 to stop the server. To remove the database containers when you're completely done, run `bash scripts/cleanup.sh` (bash) or `powershell -ExecutionPolicy Bypass -File scripts/cleanup.ps1` (PowerShell). Add `--volumes` to also delete the database data.

## Step 3 of 4: Open the Dashboard
Drasi Server's dashboard reaction hosts the live dashboard; there's no separate app to build or run. **Wait until Terminal 1 prints `Drasi Server started successfully`** (the first run takes a little longer while the plugins download), then open it in your browser:

```text
http://localhost:3000
```

In the dev container or Codespaces, port `3000` is forwarded automatically. Open the seeded **Curbside Pickup** dashboard. It has six Markdown panels: the four list panels sit side by side on the top row, with the two join panels below:

- 🍕 **Orders · Preparing** and 🍕 **Orders · Ready** - every order in PostgreSQL, split by status. An order appears in exactly one of the two, and jumps from *Preparing* to *Ready* the instant its status changes.
- 🚗 **Vehicles · Parking** and 🚗 **Vehicles · Curbside** - every vehicle in MySQL, split by location. A vehicle moves from *Parking* to *Curbside* the instant its location changes.
- 📦 **Matched Orders** - orders that are *ready* whose driver is at the *Curbside* (the `delivery` query).
- ⚠️ **Delayed Orders** - drivers who have waited at the curbside for more than 10 seconds while their order is still being prepared (the `delay` query).

At bootstrap all three orders are *preparing* and all three vehicles are in *Parking*, so those two panels list every row while their **Ready** and **Curbside** counterparts start empty. The **Matched Orders** and **Delayed Orders** panels also start **empty** - no order is *ready* and no vehicle is at the *Curbside* yet - and fill in as you drive changes. Every panel updates the instant the data changes, with no refreshing; because each panel is backed by a filtered continuous query, a row simply disappears from one panel and reappears in the other as it changes.

<img src="images/dashboard.png" width="900" alt="The Curbside Pickup dashboard with six Markdown panels: orders preparing, orders ready, vehicles parking, vehicles curbside, matched orders, and delayed orders">

## Step 4 of 4: Drive Change
You drive changes from an **operations console** that connects directly to both databases and, as you make changes, prints **every SQL statement it runs and which database it hit** - so you can see exactly what Drasi is reacting to. It comes in two flavours that do the same thing (they share the same `db.js` data-access layer); pick whichever you prefer:

- a **terminal app** (`tui/`) you drive with the keyboard, or
- a **browser console** (`webui/`) you drive with your mouse.

Both have two panels - **Retail Operations** (the PostgreSQL `orders` table) and **Physical Operations** (the MySQL `vehicles` table) - and a live SQL log. With Terminal 1 running the demo and the dashboard open, start **one** of them in **Terminal 2**.

#### Option A — Terminal console

**bash / zsh**

```bash
bash scripts/start-tui.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-tui.ps1
```

- **Tab** / **←** / **→** switch the focused panel.
- **↑** / **↓** select a row.
- **Enter** toggles the selected row: an order flips between *preparing* and *ready*; a vehicle flips between *Parking* and *Curbside*.
- **q** quits.

#### Option B — Browser console

**bash / zsh**

```bash
bash scripts/start-webui.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-webui.ps1
```

Then open **[http://localhost:3001](http://localhost:3001)**. Each row has a button that toggles it - *mark ready →* / *to Curbside →* and back - and the SQL log fills in underneath, colour-coded by database. It's the same experience as the terminal app, in the browser:

<img src="images/web-console.png" width="900" alt="The browser operations console: a Retail Operations (PostgreSQL) panel of orders and a Physical Operations (MySQL) panel of vehicles, each row with a toggle button, and a colour-coded SQL log below showing the UPDATE statements and which database they hit">

The scenarios below say "mark it *ready*" or "move it to *Curbside*" - in the terminal app that's selecting the row and pressing **Enter**; in the browser it's clicking the row's button. Either way it runs the same `UPDATE`.

### Trigger a delivery

Mark order **A1234** (Sophia Carter) *ready*. The console logs:

```text
[PostgreSQL] UPDATE orders SET status='ready' WHERE id=1;
```

Watch the dashboard: order **A1234** immediately leaves the 🍕 **Orders · Preparing** panel and appears in 🍕 **Orders · Ready**. Now move vehicle **A1234** to *Curbside*:

```text
[MySQL] UPDATE vehicles SET location='Curbside' WHERE plate='A1234';
```

The vehicle jumps from 🚗 **Vehicles · Parking** to 🚗 **Vehicles · Curbside**, and within about a second the 📦 **Matched Orders** panel reacts: order **A1234** appears with its driver and vehicle. Nothing polled anything - Drasi saw the PostgreSQL change through logical replication and the MySQL change through the binary log, and re-evaluated the cross-database join.

Move the vehicle back to *Parking* and the row disappears from **Matched Orders**: the order is no longer matched to a waiting driver.

### Trigger a delay

Now reproduce the *other* scenario. Pick a vehicle whose order is **not** ready - say **B5678** (Mason Rivera) - and move it to *Curbside*, but **leave order B5678 as *preparing***. Nothing happens immediately. After **10 seconds** the **Delayed Orders** panel lights up: order **B5678** appears, flagging that the driver has been waiting too long.

This is the interesting one. Drasi doesn't poll to find slow orders - the **continuous query schedules its own future re-evaluation** for the moment the 10-second threshold is crossed, and fires exactly then. If you mark the order *ready* (or send the driver back to *Parking*) before the 10 seconds elapse, the alert never appears.

### Reset

Return everything to the starting state (all orders *preparing*, all vehicles *Parking*):

**bash / zsh**

```bash
bash scripts/reset.sh
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/reset.ps1
```

## How It Works
Everything you just ran is described by the single `server-config.yaml`. Here's what each part does.

### Two Sources

The queries join data from two different databases, so the configuration declares two sources.

**PostgreSQL** holds the orders and streams changes via **logical replication (CDC)**:

```yaml
sources:
  - kind: postgres
    id: retail-ops
    # ... connection settings ...
    tables:
      - orders
    tableKeys:
      - table: orders
        keyColumns:
          - id
    bootstrapProvider:
      kind: postgres
```

**MySQL** holds the vehicles and streams changes via its **binary log (binlog)**. The Drasi source reads the binlog directly, so `database/docker-compose.yml` starts MySQL with ROW-based logging, full row images/metadata, and GTID mode, and `database/mysql-init.sql` grants the Drasi user the replication privileges it needs:

```yaml
  - kind: mysql
    id: physical-ops
    # ... connection settings ...
    sslMode: disabled
    tables:
      - vehicles
    tableKeys:
      - table: vehicles
        keyColumns:
          - plate
    bootstrapProvider:
      kind: mysql
      # ... the MySQL bootstrap provider takes its own connection settings ...
```

Each table row becomes a graph node. The `orders` table becomes `orders` nodes and the `vehicles` table becomes `vehicles` nodes, matching the `(o:orders)` and `(v:vehicles)` patterns in the queries.

### The Synthetic Join

There is no foreign key between the two databases - they're completely separate systems. Drasi creates the relationship in the query with a **synthetic join**, matching a vehicle to an order whenever their `plate` values are equal:

```yaml
joins:
  - id: PICKUP_BY
    keys:
      - label: vehicles
        property: plate
      - label: orders
        property: plate
```

The queries then walk that relationship with `(o:orders)-[:PICKUP_BY]->(v:vehicles)` as if it were a real graph edge - across two different databases.

### The Six Continuous Queries

Four of the queries are simple single-source lists, filtered by state, that feed the split **Orders** and **Vehicles** panels. Because each one matches only part of the table, a row leaves one query's result and joins the other's the instant its status or location changes - which is exactly what makes it hop between panels on the dashboard. `orders-preparing` and `orders-ready` split the PostgreSQL orders by status:

```cypher
MATCH (o:orders)
WHERE o.status <> 'ready'          -- orders-ready uses: o.status = 'ready'
RETURN o.id AS orderId, o.customer_name AS customerName,
       o.driver_name AS driverName, o.plate AS plate, o.status AS status
```

and `vehicles-parking` and `vehicles-curbside` split the MySQL vehicles by location:

```cypher
MATCH (v:vehicles)
WHERE v.location = 'Parking'        -- vehicles-curbside uses: v.location = 'Curbside'
RETURN v.plate AS plate, v.make AS make, v.model AS model,
       v.color AS color, v.location AS location
```

The other two join across both databases. **Delivery** returns an order whenever it is *ready* and its driver's vehicle is at the *Curbside*. The `drasi.changeDateTime` guards ignore the rows loaded at bootstrap (whose change time is epoch 0), so the dashboard starts empty and only fills in as changes are driven live:

```cypher
MATCH (o:orders)-[:PICKUP_BY]->(v:vehicles)
WHERE o.status = 'ready'
  AND v.location = 'Curbside'
  AND drasi.changeDateTime(v) != datetime({epochMillis: 0})
  AND drasi.changeDateTime(o) != datetime({epochMillis: 0})
RETURN
  o.id AS orderId,
  o.driver_name AS driverName,
  o.plate AS vehicleId,
  v.make AS vehicleMake,
  v.model AS vehicleModel,
  v.color AS vehicleColor,
  v.location AS vehicleLocation,
  drasi.listMax([drasi.changeDateTime(o), drasi.changeDateTime(v)]) AS readyTimestamp
```

**Delay** returns an order whose driver has been at the *Curbside* for more than 10 seconds while the order still isn't *ready*. It uses **`drasi.trueFor`**, which schedules a future re-evaluation and fires the moment the condition has held for the given duration, so the order appears exactly when the 10-second threshold is crossed:

```cypher
MATCH (o:orders)-[:PICKUP_BY]->(v:vehicles)
WHERE o.status <> 'ready'
WITH o, v, drasi.changeDateTime(v) AS waitingSinceTimestamp
WHERE waitingSinceTimestamp != datetime({epochMillis: 0})
  AND drasi.trueFor(v.location = 'Curbside', duration({ seconds: 10 }))
RETURN
  o.id AS orderId,
  o.customer_name AS customerName,
  waitingSinceTimestamp
```

> **How the timing works**
>
> Both the PostgreSQL and MySQL sources stamp every change with the wall-clock time it happened, which `drasi.changeDateTime()` exposes. That's what lets the queries tell a live change apart from a bootstrap row (whose change time is epoch 0) and lets `drasi.trueFor` anchor its 10-second timer - no extra timestamp columns or application bookkeeping required. The `delivery` and `delay` queries are the same as the original Kubernetes tutorial, unchanged.

### The Dashboard Reaction

A single dashboard reaction subscribes to all six queries and seeds one **Curbside Pickup** dashboard on first start. It uses six Markdown (`text`) widgets, each rendering its query's rows with a Handlebars template - no KPIs or tables to configure, just a list:

```yaml
reactions:
  - kind: dashboard
    id: curbside-dashboard
    queries:
      - orders-preparing
      - orders-ready
      - vehicles-parking
      - vehicles-curbside
      - delivery
      - delay
    port: 3000
    predefinedDashboards:
      - id: curbside-pickup
        name: Curbside Pickup
        widgets:
          - { type: text, title: "🍕 Orders · Preparing",  config: { queryId: orders-preparing } }
          - { type: text, title: "🍕 Orders · Ready",      config: { queryId: orders-ready } }
          - { type: text, title: "🚗 Vehicles · Parking",  config: { queryId: vehicles-parking } }
          - { type: text, title: "🚗 Vehicles · Curbside", config: { queryId: vehicles-curbside } }
          - { type: text, title: "📦 Matched Orders",      config: { queryId: delivery } }
          - { type: text, title: "⚠️ Delayed Orders",      config: { queryId: delay } }
```

Each `text` widget's template loops over `rows` and prints a Markdown bullet per result; when a query's result set changes, the reaction pushes the update to the browser. That's the whole UI - no front-end code to write or host.

### Driving Change

The operations console is a small Node.js app that connects straight to PostgreSQL and MySQL and runs ordinary `UPDATE` statements - the same kind your real retail and physical-operations apps would run. It ships in two forms that share the exact same `tui/src/db.js` data-access layer: a terminal UI (`tui/`, built with [Ink](https://github.com/vadimdemedes/ink)) and a browser console (`webui/`, a tiny [Express](https://expressjs.com/) server serving a static page). Both are a convenience for the tutorial, not part of Drasi: Drasi reacts to the database changes however they're made.

## Clean Up

When you're done, stop Drasi Server with **Ctrl+C** in Terminal 1, then remove the database containers:

**bash / zsh**

```bash
bash scripts/cleanup.sh --volumes
```

**PowerShell**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/cleanup.ps1 --volumes
```
