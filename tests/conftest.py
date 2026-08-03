"""Global test environment (loaded by pytest before any test module).

Guarantees the whole suite stays hermetic: the config settings singleton is
built once, at first project import, so these env vars must be in place before
any test module imports ``config``/``db``/``ui``. Otherwise a local ``.env``
with a live GROQ key would leak real LLM calls into the tests (and silently
consume the daily token quota until the rate limit breaks them).
"""

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("GROQ_MODEL", "llama-3.3-70b-versatile")
