# wiki

Wikipedia semantic search is a design-preview customer of hev layer. The public deliverable is `wiki.hevlayer.com`; the visible artifact is Layer's Lattice embedding performance echo.

Reimplement nothing the stack owns. The app does not embed, tokenize queries, fuse, or rerank. Both backends issue the same gateway `Embed` request. See `AGENTS.md` for commands and feedback routing.
