# Tool Description Review Skill

Use this workflow before exposing tools to a model or after seeing tool misuse.

1. Run `review_tool_surface` for the target profile.
2. Check profile size. Prefer fewer than 20 tools.
3. For each tool, confirm the description includes:
   - purpose
   - use_when
   - do_not_use_when
   - required_prior_state
   - output_means
   - recommended_next_tools
   - key_or_cost_notes
   - common_failure_modes
4. Look for duplicated descriptions and overlapping tools.
5. Move infrequent or expensive tools out of `agent_core`.
6. Add tests for profile membership and exported schemas.

Tool descriptions should teach decision boundaries, not just restate function names.

