"""harness -- a minimal, on-demand, tool-using agent loop over the local LLM.

Public modules:
    harness.loop      -- run(task, llm, policy, ...) -> str
    harness.registry  -- Skill, SkillResult, REGISTRY, register(), validate_args()
    harness.policy    -- RunPolicy, OnDemandReadOnly
    harness.transcript -- Transcript (typed JSONL run log)
"""
