#!/bin/zsh
# Export a .pptx to PDF with Keynote: keynote_pdf.sh in.pptx out.pdf
IN="$1"; OUT="$2"
osascript -e 'tell application "Keynote" to quit' 2>/dev/null
sleep 3
open -a Keynote "$IN"
sleep 15
osascript <<OSA
with timeout of 300 seconds
tell application "Keynote"
  set d to front document
  export d to POSIX file "$OUT" as PDF
  close d saving no
end tell
end timeout
OSA
