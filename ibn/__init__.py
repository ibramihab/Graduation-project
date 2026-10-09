"""Simple Intent-Based Networking (IBN) system.

Layers (each one is a folder):
    interface/       1. you type what you want and approve
    intent/          2. the AI understands your request
    validation/      3. checks the change is safe
    control/         4. applies it, undoes it if it fails
    infrastructure/  5. talks to the real devices (+ discovery)
    knowledge/       shared memory of the network (graph database)
"""
