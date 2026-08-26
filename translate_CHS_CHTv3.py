#!/usr/bin/env python3
import gi, subprocess
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

def run_opencc(config, text, status_label):
    """Run opencc on given text with error handling"""
    try:
        # Run opencc conversion
        result = subprocess.run(
            ["opencc", "-c", config],
            input=text, text=True, capture_output=True
        )
        
        if result.returncode != 0:
            status_label.set_text(f"❌ OpenCC error: {result.stderr.strip()}")
            return text
            
        translated = result.stdout.strip()
        
        # Update clipboard
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard"], 
                input=translated, text=True, check=True
            )
            status_label.set_text(f"✅ Converted using {config} (copied to clipboard)")
        except subprocess.CalledProcessError:
            status_label.set_text(f"✅ Converted using {config} (clipboard unavailable)")
        except FileNotFoundError:
            status_label.set_text(f"✅ Converted using {config} (xclip not found)")
            
        return translated
        
    except FileNotFoundError:
        status_label.set_text("❌ OpenCC not found. Please install opencc.")
        return text
    except Exception as e:
        status_label.set_text(f"❌ Error: {str(e)}")
        return text

def auto_translate(widget, textview, status_label):
    """Auto-detect and translate between Traditional/Simplified Chinese"""
    buffer = textview.get_buffer()
    start, end = buffer.get_bounds()
    text = buffer.get_text(start, end, True)
    
    if not text.strip():
        status_label.set_text("⚠️ No text to translate")
        return
    
    # Detect if text contains Traditional Chinese characters
    if any(ch in text for ch in "龜龍馬臺灣國體漢繁聲點對關際復歲層額題雜約證標線難個與業號種廳產愛處買計黨團網讓華術語識總圖請選結機會聯員製術國當場門長"):
        translated = run_opencc("t2s.json", text, status_label)
    else:
        translated = run_opencc("s2t.json", text, status_label)
    
    buffer.set_text(translated)

def to_traditional(widget, textview, status_label):
    """Convert text to Traditional Chinese"""
    buffer = textview.get_buffer()
    start, end = buffer.get_bounds()
    text = buffer.get_text(start, end, True)
    
    if not text.strip():
        status_label.set_text("⚠️ No text to translate")
        return
        
    translated = run_opencc("s2t.json", text, status_label)
    buffer.set_text(translated)

def to_simplified(widget, textview, status_label):
    """Convert text to Simplified Chinese"""
    buffer = textview.get_buffer()
    start, end = buffer.get_bounds()
    text = buffer.get_text(start, end, True)
    
    if not text.strip():
        status_label.set_text("⚠️ No text to translate")
        return
        
    translated = run_opencc("t2s.json", text, status_label)
    buffer.set_text(translated)

def clear_text(widget, textview, status_label):
    """Clear the text area"""
    buffer = textview.get_buffer()
    buffer.set_text("")
    status_label.set_text("🗑️ Text cleared")

def quit_app(_):
    """Quit the application"""
    Gtk.main_quit()

class TranslateApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Chinese Translator")
        self.set_default_size(600, 400)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Create status label first
        self.status_label = Gtk.Label(label="ℹ️ Ready")
        self.status_label.set_halign(Gtk.Align.START)
        
        # Main container
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(15)
        vbox.set_margin_bottom(15)
        vbox.set_margin_start(15)
        vbox.set_margin_end(15)
        
        # Text area with frame
        text_frame = Gtk.Frame()
        text_frame.set_label("Text to translate")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.textview = Gtk.TextView()
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.textview.set_margin_top(5)
        self.textview.set_margin_bottom(5)
        self.textview.set_margin_start(5)
        self.textview.set_margin_end(5)
        scrolled.add(self.textview)
        text_frame.add(scrolled)
        vbox.pack_start(text_frame, True, True, 0)
        
        # Button container
        button_box = Gtk.Box(spacing=8)
        button_box.set_homogeneous(True)
        
        # Translation buttons
        btn_auto = Gtk.Button(label="🔄 Auto Translate")
        btn_auto.set_tooltip_text("Automatically detect and convert between Traditional/Simplified")
        btn_auto.connect("clicked", auto_translate, self.textview, self.status_label)
        button_box.pack_start(btn_auto, True, True, 0)
        
        btn_trad = Gtk.Button(label="📗 To Traditional")
        btn_trad.set_tooltip_text("Convert to Traditional Chinese")
        btn_trad.connect("clicked", to_traditional, self.textview, self.status_label)
        button_box.pack_start(btn_trad, True, True, 0)
        
        btn_simp = Gtk.Button(label="📘 To Simplified")
        btn_simp.set_tooltip_text("Convert to Simplified Chinese")
        btn_simp.connect("clicked", to_simplified, self.textview, self.status_label)
        button_box.pack_start(btn_simp, True, True, 0)
        
        # Utility buttons
        btn_clear = Gtk.Button(label="🗑️ Clear")
        btn_clear.set_tooltip_text("Clear all text")
        btn_clear.connect("clicked", clear_text, self.textview, self.status_label)
        button_box.pack_start(btn_clear, True, True, 0)
        
        btn_quit = Gtk.Button(label="❌ Quit")
        btn_quit.set_tooltip_text("Exit application")
        btn_quit.connect("clicked", quit_app)
        button_box.pack_start(btn_quit, True, True, 0)
        
        vbox.pack_start(button_box, False, False, 0)
        
        # Status bar at bottom
        status_frame = Gtk.Frame()
        status_box = Gtk.Box()
        status_box.set_margin_top(5)
        status_box.set_margin_bottom(5)
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)
        status_box.pack_start(self.status_label, False, False, 0)
        status_frame.add(status_box)
        vbox.pack_start(status_frame, False, False, 0)
        
        self.add(vbox)

def main():
    app = TranslateApp()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()

