import re
import os

input_file = 'Forti_SASE_full_ZH.md'
output_dir = 'Forti_SASE_Course'

def main():
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by "## Page N"
    pages = re.split(r'(?m)^(## Page \d+\s*\n)', content)

    if len(pages) < 2:
        print("Error processing file, pages not found.")
        return

    header = pages[0]
    pages = pages[1:]

    slides = []
    for i in range(0, len(pages), 2):
        if i+1 < len(pages):
            slides.append(pages[i] + pages[i+1])

    print(f"Total slides found: {len(slides)}")

    PAGES_PER_CHAPTER = 40
    chapters = []
    for i in range(0, len(slides), PAGES_PER_CHAPTER):
        chapters.append(slides[i:i+PAGES_PER_CHAPTER])

    for idx, chapter_slides in enumerate(chapters):
        chapter_num = idx + 1
        filename = os.path.join(output_dir, f'Chapter_{chapter_num:02d}.md')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# Module {chapter_num}: Forti SASE Course\n\n")
            f.write(header if chapter_num == 1 else "")
            f.write("".join(chapter_slides))

    # Create an index/course outline file
    with open(os.path.join(output_dir, 'README.md'), 'w', encoding='utf-8') as f:
        f.write("# Forti SASE Course Outline\n\n")
        f.write("This course is generated from the Forti SASE presentation slides.\n\n")
        for idx, chapter_slides in enumerate(chapters):
            chapter_num = idx + 1
            num_slides = len(chapter_slides)
            start_page = idx * PAGES_PER_CHAPTER + 1
            end_page = start_page + num_slides - 1
            f.write(f"- [Module {chapter_num}](./Chapter_{chapter_num:02d}.md) (Pages {start_page} - {end_page})\n")

    print(f"Splitting complete. Files written to {output_dir}")

if __name__ == '__main__':
    main()
