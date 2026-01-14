"""Distributed supermarket queue management system (MQTT-based).

Project v0 uses MQTT pub/sub (via a broker like Mosquitto) to coordinate:
- a Queue Manager service
- multiple Checkout agents
- Customer clients
- an optional Customer Generator (Poisson arrivals) for load testing / simulation

See README for how to run.
"""
