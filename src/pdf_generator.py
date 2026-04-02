import os
import markdown
import pdfkit
import platform

def generate_pdf(markdown_text: str, filename: str = "research_report.pdf"):
    """Converts a markdown string into a styled PDF document using pdfkit."""
    
    # 1. Ensure an output directory exists
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    
    # 2. Convert Markdown to HTML
    html_content = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
    
    # 3. Add Professional CSS Styling
    css_style = """
    <style>
        body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333; line-height: 1.6; margin: 40px; }
        h1 { color: #2C3E50; border-bottom: 2px solid #34495E; padding-bottom: 5px; }
        h2 { color: #2980B9; margin-top: 30px; }
        h3 { color: #7F8C8D; }
        p { margin-bottom: 15px; }
        ul, ol { margin-bottom: 20px; }
        li { margin-bottom: 8px; }
        code { background-color: #F8F9F9; padding: 2px 5px; border-radius: 4px; font-family: monospace; }
        pre code { display: block; padding: 15px; background-color: #F4F6F7; border-left: 4px solid #BDC3C7; }
        blockquote { border-left: 4px solid #2980B9; margin: 0; padding-left: 15px; color: #555; font-style: italic; }
    </style>
    """
    
    # 4. Combine HTML and CSS
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        {css_style}
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # 5. Dynamic path for wkhtmltopdf
    if platform.system() == "Windows":
        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    else:
        # This is the path where Docker/Linux installs it
        config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    
    # 6. Render and save!
    print("--- GENERATING PDF ---")
    
    # pdfkit requires some options to suppress console spam
    options = {'quiet': ''}
    pdfkit.from_string(full_html, filepath, configuration=config, options=options)
    
    print(f"--- PDF SAVED SUCCESSFULLY TO: {filepath} ---")
    
    return filepath