from pathlib import Path
import re
import sys

verbose = False
checkBadIndenting = True
verboseBadIndenting = True

# Check the following:
#   - consistent line endings throughout file
#   - no tabs in c, h, cpp files
#   - leading whitespace is a multiple of 4
#   - no trailing whitespace
#   - no non-ASCII or weird control characters
#   - end of line at end of file

class Status:
    def __init__(self, path, hasInconsistentLineEndings=False, hasTabs=False, hasBadIndenting=False, hasTrailingWhitespace=False, hasBadCharacter=False, hasNoEolAtEof=False):
        self.path = path
        self.hasInconsistentLineEndings = hasInconsistentLineEndings
        self.hasTabs = hasTabs
        self.hasBadIndenting = hasBadIndenting
        self.hasTrailingWhitespace = hasTrailingWhitespace
        self.hasBadCharacter = hasBadCharacter
        self.hasNoEolAtEof = hasNoEolAtEof

    def isBad(self):
        return len(self.issueSummary()) > 0

    def issueSummary(self):
        result = []
        if self.hasInconsistentLineEndings:
            result += ["has-inconsistent-line-endings"]
        if self.hasTabs:
            result += ["has-tabs"]
        if self.hasBadIndenting:
            result += ["has-bad-indenting"]
        if self.hasTrailingWhitespace:
            result += ["has-trailing-whitespace"]
        if self.hasBadCharacter:
            result += ["has-bad-character"]
        if self.hasNoEolAtEof:
            result += ["has-no-eol-at-eof"]
        return str.join(", ", result)

def multilineCommentIsOpen(lineText, wasOpen):
    isOpen = wasOpen
    index = 0
    end = len(lineText)
    while index != -1 and index < end:
        if isOpen:
            index = lineText.find(b'*/', index)
            if index != -1:
                isOpen = False
                index += 2
        else:
            index = lineText.find(b'/*', index)
            if index != -1:
                isOpen = True
                index += 2
    return isOpen

# A line allows an unusual indent to follow if it is the beginning of a
# multi-line function parameter list, or an element of a function parameter list.
def allowsStrangeIndentOnFollowingLine(lineText):
    s = lineText.strip(b' ')
    if len(s) == 0:
        return False

    if s.rfind(b'*/') == (len(s) - 2): # line has a trailing comment, strip it
        commentStart = s.rfind(b'/*')
        if commentStart != -1:
            s = s[:commentStart].strip(b' ')
            if len(s) == 0:
                return False

        if len(s) == 0:
            return False

    okChars = b'(,+-/*='
    if s[-1] in okChars: # program text is trailing '(' or ',' etc.
        return True
    return False


statusSummary = []

filetypes = ["*.c", "*.h", "*.cpp"]
for ext in filetypes:
    for path in Path('src').rglob(ext):
        if "ASIOSDK" in path.parts or "mingw-include" in path.parts:
            continue

        data = path.read_bytes()

        status = Status(path)
        statusSummary.append(status)

        # 1. Consistent line endings
        # check for stray CR or LF, then convert CRLF to LF
        assert(not b'\f' in data) # we'll use \f as a sentinel
        if b'\r' in data and b'\n' in data:
            d = data.replace(b'\r\n', b'\f')
            if b'\r' in d:
                status.hasInconsistentLineEndings = True
                if verbose:
                    print("error: " + str(path) + " stray carriage return")
            if b'\n' in d:
                status.hasInconsistentLineEndings = True
                if verbose:
                    print("error: " + str(path) + " stray newline")

            data = d.replace(b'\f', b'\n') # normalize line endings

        # 2. absence of tabs
        if b'\t' in data:
            status.hasTabs = True
            if verbose:
                print("error: " + str(path) + " contains tab")

            data = data.replace(b'\t', b'    ') # normalize tabs to 4 spaces

        # 3. leading whitespace / bad indenting
        if checkBadIndenting:
            leadingWhitespaceRe = re.compile(b'^\s*')
            lines = data.split(b'\n') # relies on normalization above
            commentIsOpen = False
            previousLine = b''
            previousIndent = 0
            lineNo = 1
            for line in lines:
                if commentIsOpen:
                    # don't check leading whitespace inside comments
                    commentIsOpen = multilineCommentIsOpen(line, commentIsOpen)
                    previousIndent = 0
                else:
                    m = leadingWhitespaceRe.search(line)
                    indent = m.end() - m.start()
                    if indent != len(line): # ignore whitespace lines, they are considered trailing whitespace
                        if indent % 4 is not 0 and indent != previousIndent: # potential bad indents are not multiples of 4, and are not indented the same as the previous line
                            s = previousLine
                            if not allowsStrangeIndentOnFollowingLine(previousLine):
                                status.hasBadIndenting = True
                                if verbose or verboseBadIndenting:
                                    print("error: " + str(path) + "(" + str(lineNo) + ")" + " bad indent: " + str(indent))
                                    print(line)
                    commentIsOpen = multilineCommentIsOpen(line, commentIsOpen)
                    previousIndent = indent
                previousLine = line
                lineNo += 1

        # 4. trailing whitespace
        trailingWhitespaceRe = re.compile(b'\s*$')
        lines = data.split(b'\n') # relies on normalization above
        lineNo = 1
        for line in lines:
            m = trailingWhitespaceRe.search(line)
            trailing = m.end() - m.start()
            if trailing > 0:
                status.hasTrailingWhitespace = True
                if verbose:
                    print("error: " + str(path) + "(" + str(lineNo) + ")" + " trailing whitespace: ")
                    print(line)
            lineNo += 1

        # 5. non-ASCII or weird control characters
        badCharactersRe = re.compile(b'[^\t\r\n\x20-\x7E]+')
        lines = data.split(b'\n') # relies on normalization above
        lineNo = 1
        for line in lines:
            m = badCharactersRe.search(line)
            if m:
                bad = m.end() - m.start()
                if bad > 0:
                    status.hasBadCharacter = True
                    if verbose:
                        print("error: " + str(path) + "(" + str(lineNo) + ")" + " bad character: ")
                        print(line)
            lineNo += 1

        # 6. check for EOL at EOF
        if len(data) > 0:
            lastChar = data[-1]
            if lastChar != b'\n'[0]:
                status.hasNoEolAtEof = True
                if verbose:
                    print("error: " + str(path) + " no end-of-line at end-of-file")


print("SUMMARY")
print("=======")
badness = False
for s in statusSummary:
    if s.isBad():
        badness = True
        print("error: " + str(s.path) + " (" + s.issueSummary() + ")")

if badness:
    sys.exit(1)
else:
    sys.exit(0)
