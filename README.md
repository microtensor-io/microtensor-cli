# microtensor-cli

The mt command for Microtensor customers.

A light package with no miner or validator dependencies. It talks to
api.microtensor.cloud with an API key and covers the registry (pull a certified
artifact and verify it against its certificate), batch jobs, evaluations and
key management.

The subnet package plugs its miner and validator commands into this one, so a
single mt command serves both audiences.
