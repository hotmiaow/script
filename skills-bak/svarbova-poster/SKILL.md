---
name: svarbova-poster
description: Generate high-end editorial posters inspired by Maria Svarbova's color and composition logic. Use when the user requests "svarbova-poster", "斯瓦波娃", "高级编辑海报", or asks for editorial posters with geometric spaces, quiet figures, retro mint/blue palettes, and integrated giant titles.
---

# Maria Svarbova Editorial Poster Generator

Generate a high-end editorial poster that integrates text and imagery, styled after Maria Svarbova's distinct aesthetic: calm, restrained, geometric public spaces, and figures serving as symbols of order.

## Parameters

The skill accepts the following inputs (prompt the user if any are missing or unclear):

- **比例 (Aspect Ratio)**: [5:2 / 16:9 / 3:4]
- **主標題 (Main Title)**: [Required, giant text integrated into screen structure]
- **副標題 (Subtitle)**: [Optional, recommended within one sentence]
- **場景 (Scene)**: [Specific geometric public space, e.g., tiled swimming pool, colonnade]
- **核心隱喻 (Core Metaphor)**: [A concrete action or object, e.g., standing still, looking down, holding a balloon]

## Workflow

### Step 1: Intake & Parameter Resolution

Read the user's request. If any parameters are missing, ask the user to fill them in. Default to `3:4` if aspect ratio is not specified.

### Step 2: Prompt Engineering for Image Generation

Synthesize a detailed prompt for the `generate_image` tool. Do not just paste the parameters; translate them into a descriptive scene following these style rules:

1. **Aesthetics & Composition**: Calm, restrained, geometric public space. Use clean tiles, steps, door frames, columned corridors, minimalist chairs, walls, and water reflections. Ensure a strong sense of order and ample negative space (whitespace).
2. **Figures**: Few figures (typically one or two), with neutral, calm expressions (no smiling, no dramatization). Figures should look like orderly symbols positioned to complement the geometry of the space.
3. **Color Palette**: Dominated by mint green, ice blue, cream white, and light wood tones. Use small tomato red or coral red accents as visual anchors. The color temperature should be bright, clean, retro, and restrained.
4. **Text & Typography**:
   - The **Main Title** must be giant, written in tomato red or dark teal/cyan, and integrated naturally into the architectural grid/structure of the scene (e.g., painted on a tiled wall, aligned with a pillar).
   - The **Subtitle** should be small, appear once, and sit cleanly near the main title or at the bottom.
   - You may include up to one tiny block of auxiliary text matching the theme, but no more.
5. **Strict Prohibitions (Negative Prompt Elements)**:
   - NO barcode, data icons, percentages, information columns, document numbers, or stacked magazine text.
   - Avoid generic PPT layouts, cheap technology elements, or element cluttering.
   - The final output must look like a high-end integrated editorial cover/poster, not a generic overlay of text on top of an image.

### Step 3: Run Generation

Call the `generate_image` tool with the compiled prompt.
- **ImageName**: `svarbova_poster_[slug]` (where slug is 1-2 words from the main title, lowercase with underscores).
- **AspectRatio**: Map the ratio chosen: `5:2` (use `16:9` if unsupported, or closest), `16:9`, `3:4`.
- **Prompt**: Write the generated prompt in English for maximum compatibility with the image generation models.

### Step 4: Display & Report

Present the generated poster to the user and list the parameters used. Indicate where the file is stored.

## Example Prompts

### Example 1 (3:4 Ratio)

**Input**:
- Ratio: `3:4`
- Main Title: `REST`
- Subtitle: `Quiet moment in the public bath`
- Scene: `A minimalist public indoor swimming pool`
- Metaphor: `A woman sitting on a step looking at the water`

**Generated Prompt for `generate_image`**:
> A high-end editorial art poster in the style of Maria Svarbova, ratio 3:4. A minimalist public indoor swimming pool characterized by clean rectangular tiles, geometric columns, and calm water reflecting soft light. A single woman in a vintage mint green swimsuit sits quietly on a tiled step, looking down at the water with a neutral, calm expression, acting as a symbol of order in the space. The color palette is dominated by ice blue, mint green, cream white, and light wood, with a small tomato red visual anchor on her swimming cap. The giant title "REST" is rendered in bold, clean sans-serif tomato red lettering, integrated into the vertical grid of the tiled wall. The small subtitle "Quiet moment in the public bath" is printed in clean, small dark letters beneath it. High-end magazine cover feel, minimal art photography, clean negative space. No barcodes, no icons, no tech elements, no clutter.
