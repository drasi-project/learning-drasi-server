---
type: "docs"
title: "Setup: GitHub Codespace"
linkTitle: "GitHub Codespace"
weight: 10
toc_hide: true
description: "Source requirements for remote tutorial environments"
---

The Getting Started tutorial requires the matching **local Server and Core
sources**, including any uncommitted changes, and separately built plugins.
A one-click Codespace for this repository alone does not contain those
sources. The previous released-binary Codespace setup is not equivalent and
is no longer used by this tutorial.

Use the [local Dev Container](../dev-container/) or
[local source build](../download-binary/) with your existing sibling checkouts.
This setup does not upload your work or clone replacement repositories.

A deliberately prepared remote environment must have the same sibling layout
and matching source contents before building. Its maintainer must provide
that layout and a working Podman environment; the local parent-directory bind
mount configuration is not a one-click remote provisioning recipe.
Run Server, SQL helpers, and SSE CLI in that same environment, and use private
port forwarding to view results. Do not make the unauthenticated tutorial
API, SSE, HTTP Source, or database public.

[Return to Getting Started](../#setup).
