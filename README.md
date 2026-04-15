# A2A Multi-Turn Conversation — Single Trace with MLflow

A Python proof-of-concept (POC) demonstrating how to trace **multi-turn 
Agent-to-Agent (A2A) conversations** as a **single unified MLflow trace**. 
Instead of generating one trace per turn, this approach groups all conversation 
turns under one session trace — enabling end-to-end LLM observability, 
conversation-level evaluation, and debugging across the full interaction history.

Built with **MLflow Tracing**, compatible with any LLM or agent framework.
