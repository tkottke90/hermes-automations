# Op: Query the Wiki

Orientation (SKILL.md Step 2) must be complete before starting here.

---

## Standard Query

① Index.md was already read during orientation — identify which pages are relevant.

② For large wikis (100+ pages), also search across all `.md` files for key terms:
```bash
grep -r "<key terms>" "<wiki_path>" --include="*.md" -l
```

③ Read the relevant pages using `read_file`.

④ Synthesize an answer from the compiled knowledge. Cite the wiki pages you drew from:
   "Based on [[page-a]] and [[page-b]]..."

⑤ File valuable answers back to `queries/` — only if the answer is a substantial comparison,
   deep dive, or novel synthesis that would be painful to re-derive. Don't file trivial lookups.

⑥ Update log.md:
```bash
python ~/.hermes/skills/custom/llm-wiki/scripts/wiki-nav-update.py "<wiki_path>" \
  --log "query | <topic>" [--files "queries/answer-page.md"]
```

---

## Plan Generation Variant

When the user asks to turn wiki knowledge into a personalized, actionable plan:

① **Infer goals from the wiki first** — read accumulated entity/concept pages and synthesize what
   the user's goals appear to be. State these explicitly before building anything.

② **Ask exactly the clarifying questions that would change the plan** — identify the 2–4 variables
   that most determine the plan's shape (baseline, time, constraints). One targeted question beats
   five vague ones.

③ **Build the plan from wiki concepts** — each section traces back to a wiki page. The plan is an
   application of the wiki, not a general-purpose recommendation. Cross-link every section.

④ **File as `queries/plan-name-v1.md`** — include a header block recording the user inputs
   (goals, constraints, baseline) so future sessions know what the plan was built for.

⑤ **Defer add-ons explicitly** — if the wiki has advanced content the user isn't ready for,
   name it and give a concrete milestone. Don't silently drop it.
