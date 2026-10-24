"""Agents. The engine builds them from AgentSpecs (testbed.engine.factory):
kind "scripted" -> scripted.make_agent, kind "llm" -> llm.make_agent.

Nothing is imported here, so scripted-only runs never import provider SDKs.
"""
