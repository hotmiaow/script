#!/usr/bin/env python3
import sys
import os
import argparse
from pathlib import Path

try:
    import objc
    import Vision
    import Quartz
    import Cocoa
except ImportError:
    print("Error: PyObjC is not installed. Please run:")
    print("pip install pyobjc-core pyobjc-framework-Vision pyobjc-framework-Quartz pyobjc-framework-Cocoa")
    sys.exit(1)


def recognize_text_from_cgimage(cg_image, languages=None):
    """
    Extracts text from a CGImage using Apple's Vision framework.
    """
    # 1. Create a request
    request = Vision.VNRecognizeTextRequest.alloc().init()
    # Use accurate recognition (instead of fast)
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    if languages:
        request.setRecognitionLanguages_(languages)
    
    # 2. Create request handler
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    
    # 3. Perform the request
    success, error = handler.performRequests_error_([request], None)
    if not success:
        print(f"Vision request failed: {error}")
        return ""
    
    # 4. Extract results
    extracted_text = []
    for observation in request.results():
        # Get the top candidate string
        top_candidate = observation.topCandidates_(1)[0]
        extracted_text.append(top_candidate.string())
        
    return "\n".join(extracted_text)


def nsimage_to_cgimage(ns_image):
    """
    Converts Cocoa.NSImage to Quartz.CGImage.
    """
    cg_image, rect = ns_image.CGImageForProposedRect_context_hints_(None, None, None)
    return cg_image


def process_image(image_path, output_file, languages=None):
    """
    Process a single image file.
    """
    print(f"Processing image: {image_path}")
    image_url = Cocoa.NSURL.fileURLWithPath_(str(image_path))
    ns_image = Cocoa.NSImage.alloc().initWithContentsOfURL_(image_url)
    if ns_image is None:
        print(f"Failed to load image at {image_path}")
        return
        
    cg_image = nsimage_to_cgimage(ns_image)
    text = recognize_text_from_cgimage(cg_image, languages=languages)
    
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(text + "\n\n")


def process_pdf(pdf_path, output_file, chunk_size=10, scale_factor=2.0, languages=None):
    """
    Process a PDF file by rendering pages to images and running OCR.
    Handles memory efficiently using chunking and objc.autorelease_pool().
    """
    print(f"Processing PDF: {pdf_path}")
    pdf_url = Cocoa.NSURL.fileURLWithPath_(str(pdf_path))
    pdf_doc = Quartz.PDFDocument.alloc().initWithURL_(pdf_url)
    
    if pdf_doc is None:
        print(f"Failed to load PDF at {pdf_path}")
        return
        
    page_count = pdf_doc.pageCount()
    print(f"Total pages: {page_count}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Extracted Text from {pdf_path.name}\n\n")
    
    # Process in chunks to avoid memory blowing up
    for chunk_start in range(0, page_count, chunk_size):
        chunk_end = min(chunk_start + chunk_size, page_count)
        print(f"Processing pages {chunk_start + 1} to {chunk_end}...")
        
        chunk_text = []
        # Use autorelease pool to cleanup ObjC objects created in this chunk
        with objc.autorelease_pool():
            for i in range(chunk_start, chunk_end):
                page = pdf_doc.pageAtIndex_(i)
                if page is None:
                    continue
                    
                # Get page dimensions
                media_box = page.boundsForBox_(Quartz.kPDFDisplayBoxMediaBox)
                width = media_box.size.width * scale_factor
                height = media_box.size.height * scale_factor
                
                # Render page to NSImage (scaled up for better OCR)
                target_size = Cocoa.NSMakeSize(width, height)
                ns_image = page.thumbnailOfSize_forBox_(target_size, Quartz.kPDFDisplayBoxMediaBox)
                if not ns_image:
                    continue
                    
                # Convert to CGImage
                cg_image = nsimage_to_cgimage(ns_image)
                if not cg_image:
                    continue
                    
                # Run OCR
                page_text = recognize_text_from_cgimage(cg_image, languages=languages)
                
                # Format output
                chunk_text.append(f"## Page {i + 1}\n\n{page_text}\n\n")
                
        # Write chunk to file
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write("".join(chunk_text))
            
    print(f"PDF processing complete. Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Extract text from PDF or Image using Apple's native Vision OCR")
    parser.add_argument("input", help="Path to input PDF or image file")
    parser.add_argument("-o", "--output", help="Path to output markdown file", default=None)
    parser.add_argument("-c", "--chunk-size", type=int, default=10, help="Number of pages to process at a time (PDFs only) to manage memory")
    parser.add_argument("-l", "--languages", type=str, default="en-US,zh-Hans,zh-Hant", help="Comma-separated list of language codes for OCR (e.g. en-US,zh-Hans,zh-Hant)")
    
    args = parser.parse_args()
    input_path = Path(args.input)
    languages = args.languages.split(",") if args.languages else None
    
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)
        
    output_path = args.output
    if not output_path:
        base_name = input_path.stem
        output_path = f"{base_name}_extracted.md"
        
    # Check if it's a PDF
    if input_path.suffix.lower() == '.pdf':
        process_pdf(input_path, output_path, chunk_size=args.chunk_size, languages=languages)
    else:
        # Assume it's an image
        # Write header
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# Extracted Text from {input_path.name}\n\n")
        process_image(input_path, output_path, languages=languages)
        print(f"Image processing complete. Results saved to {output_path}")

if __name__ == "__main__":
    main()
