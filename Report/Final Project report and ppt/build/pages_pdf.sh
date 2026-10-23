#!/bin/bash
# docx -> pdf through Apple Pages (no Word/LibreOffice on this Mac). Usage: pages_pdf.sh in.docx out.pdf
IN="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUTP="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
osascript <<OSA
tell application "Pages"
    launch
    activate
    delay 3
    set d to open (POSIX file "$IN")
    delay 2
    export d to (POSIX file "$OUTP") as PDF
    close d saving no
end tell
OSA
