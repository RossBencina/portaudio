from pathlib import Path
import re

verbose = False

# Check the following:
#   - consistent line endings throughout file
#   - no tabs in c, h, cpp files
#   - leading whitespace is a multiple of 4
#   - no trailing whitespace
#   - no non-ASCII or weird control characters

class Status:
    def __init__(self, path, hasInconsistentLineEndings=False, hasTabs=False, hasBadIndenting=False, hasTrailingWhitespace=False, hasBadCharacter=False):
        self.path = path
        self.hasInconsistentLineEndings = hasInconsistentLineEndings
        self.hasTabs = hasTabs
        self.hasBadIndenting = hasBadIndenting
        self.hasTrailingWhitespace = hasTrailingWhitespace
        self.hasBadCharacter = hasBadCharacter

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
        return str.join(", ", result)

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

        # 3. leading whitespace
        # leadingWhitespaceRe = re.compile(b'^\s*')
        # lines = data.split(b'\n') # relies on normalization above
        # for line in lines:
        #     m = leadingWhitespaceRe.search(line)
        #     indent = m.end() - m.start()
        #     if indent % 4 is not 0:
        #         status.hasBadIndenting = True
        #         if verbose:
        #             print("error: " + str(path) + bad indent: " + str(indent))
        #             print(line)

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




print("SUMMARY")
print("=======")
for s in statusSummary:
    if s.isBad():
        print("error: " + str(s.path) + " (" + s.issueSummary() + ")")
