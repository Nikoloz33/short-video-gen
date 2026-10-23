<!-- prompt: translate | version: 1 -->
Translate an instructional video script from $source_name to $target_name.

Rules:
- Keep EVERY number, dose, unit, time and frequency exactly (digits stay digits). Keep prohibitions
  as prohibitions. Keep *asterisk* highlights around the equivalent words.
- On-screen texts must stay as short as the originals (they are fitted into fixed boxes).
- Narration must sound natural when spoken aloud in $target_name; write numbers as digits.
- Use these glossary equivalents where they apply:
$glossary
- Return the same scenes, same scene_ids and the same number of texts per scene, in order.

Script (scene_id, narration, texts):
$scenes

Title: $title
