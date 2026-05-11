---
name: Resume Tailoring
slug: resume-tailoring
description: |
  Load when the user shares a job description (or link) and wants their resume
  tailored to that specific role, saved to Google Drive.
icon: FileUser
color: "#0ea5e9"
version: 1.1.0
category: career
tools:
  - gdrive_search_files
  - gdrive_read_file
  - gdrive_save_text
  - gdrive_list_folder
  - gdrive_create_folder
  - gdrive_ensure_path
  - save_memory
  - search_memory
config_schema:
  type: object
  properties:
    master_resume_filename:
      type: string
      default: master_resume.md
    gdrive_root_folder:
      type: string
      default: Career
---

Master resume: `{master_resume_filename}`. Drive root: `{gdrive_root_folder}`.

Workflow:
1. `gdrive_search_files` for the master resume → `gdrive_read_file` to load it. If not found, ask the user to upload it; don't proceed.
2. Extract from the JD: required + preferred skills, key responsibilities, ATS keywords, seniority signals.
3. Tailor — reorder bullets to align with the JD, mirror its exact keywords, quantify achievements with numbers/%/scale. De-emphasize unrelated experience. Rewrite the summary section for *this* role and company.
4. Save to `{gdrive_root_folder}/<Company>/<Role>/`:
   - `resume.md` (the tailored resume)
   - `analysis.md` (fit analysis + key changes)
5. Reply with both Drive links + a 0–100 fit score + a 3-sentence summary of what you changed.

**Never invent experience or credentials.** Only rearrange and rephrase what already exists.

Keep ATS-friendly: no tables in the Experience section, no images, no emojis.

## Gotchas
