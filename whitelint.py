from pathlib import Path
import re
import sys

verbose = True
checkBadIndenting = True
verboseBadIndenting = True

# Check the following:
#   1. consistent line endings throughout file
#   2. no tabs in c, h, cpp files
#   3. indenting: leading whitespace is usually a multiple of 4 spaces,
#      with permissive exceptions for continuation lines.
#   4. no trailing whitespace
#   5. no non-ASCII or weird control characters
#   6. end of line is present at end of file


class FileStatus:
    """Issue status for a particular file. Stores issue counts for each type of issue."""
    def __init__(self, path):
        self.path = path
        issueNames = [
            "has-inconsistent-line-endings",
            "has-tabs",
            "has-bad-indenting",
            "has-trailing-whitespace",
            "has-bad-character",
            "has-no-eol-at-eof",
        ]
        self.issueCounts = dict.fromkeys(issueNames, 0)

    def incrementIssueCount(self, issueName):
        assert issueName in self.issueCounts # catch typos in issueName
        self.issueCounts[issueName] += 1

    def issueSummaryString(self):
        return str.join(", ", [name for name in self.issueCounts if self.issueCounts[name] > 0])

    def hasIssues(self):
        return any(count > 0 for count in self.issueCounts.values())


def multilineCommentIsOpenAtEol(lineText, wasOpenAtStartOfLine):
    isOpen = wasOpenAtStartOfLine
    index = 0
    end = len(lineText)
    while index != -1 and index < end:
        if isOpen:
            index = lineText.find(b"*/", index)
            if index != -1:
                isOpen = False
                index += 2
        else:
            index = lineText.find(b"/*", index)
            if index != -1:
                isOpen = True
                index += 2
    return isOpen


def allowStrangeIndentOnFollowingLine(lineText):
    """Compute whether a non-standard indent is allowed on the following line.
    A line allows an unusual indent to follow if it is the beginning of a
    multi-line function parameter list, an element of a function parameter list,
    or an incomplete expression (binary operator, etc.).
    """
    s = lineText.strip(b" ")
    if len(s) == 0:
        return False
    if s.rfind(b"*/") == (len(s) - 2):  # line has a trailing comment, strip it
        commentStart = s.rfind(b"/*")
        if commentStart != -1:
            s = s[:commentStart].strip(b" ")
            if len(s) == 0:
                return False

        if len(s) == 0:
            return False

    okChars = b'(,\\+-/*=&|?:"'
    if s[-1] in okChars: # non-comment program text has trailing okChar: '(' or ',' etc.
        return True
    return False


def allowStrangeIndentOfLine(lineText):
    """Compute whether a non-standard indent is allowed on the line.
    A line is allowed an unusual indent if it is the continuation of an
    incomplete expression (binary operator, etc.).
    """
    s = lineText.strip(b" ")
    if len(s) == 0:
        return False

    okChars = b'+-/*=&|?:)"'
    if s[0] in okChars:
        return True
    return False


statusSummary = []

filetypes = ["*.c", "*.h", "*.cpp", "*.cxx", "*.hxx"]
dirs = ["src", "include", "examples", "test", "qa"] # bindings, pablio
for dir in dirs:
    for ext in filetypes:
        for path in Path(dir).rglob(ext):
            if (
                "ASIOSDK" in path.parts
                or "iasiothiscallresolver.cpp" in path.parts
                or "iasiothiscallresolver.h" in path.parts
                or "mingw-include" in path.parts
            ):
                continue

            # for testing, uncomment the following lines and select a specific path:
            #if not "qa" in path.parts:
            #    continue

            data = path.read_bytes()

            status = FileStatus(path)
            statusSummary.append(status)

            # 1. Consistent line endings
            # check and then normalize to \n line endings for the benefit of the rest of the program
            if b"\r" in data and b"\n" in data:
                # CRLF (Windows) case: check for stray CR or LF, then convert CRLF to LF
                assert not b"\f" in data  # we'll use \f as a sentinel during conversion
                d = data.replace(b"\r\n", b"\f")
                if b"\r" in d:
                    status.incrementIssueCount("has-inconsistent-line-endings")
                    if verbose:
                        print("error: {0} stray carriage return".format(path))
                if b"\n" in d:
                    status.incrementIssueCount("has-inconsistent-line-endings")
                    if verbose:
                        print("error: {0} stray newline".format(path))
                data = d.replace(b"\f", b"\n")  # normalize line endings
            elif b"\r" in data:
                # CR (Classic Mac) case: convert CR to LF
                data = d.replace(b"\r", b"\n")  # normalize line endings
            else:
                # LF (Unix) case: no change
                pass

            lines = data.split(b"\n")  # relies on newline normalization above

            # 2. absence of tabs
            lineNo = 1
            for line in lines:
                if b"\t" in line:
                    status.incrementIssueCount("has-tabs")
                    if verbose:
                        print("error: {0}({1}) contains tab".format(path, lineNo))
                lineNo += 1

            data = data.replace(b"\t", b"    ") # normalize tabs to 4 spaces for indent algorithm below
            lines = data.split(b"\n") # recompute lines, relies on newline normalization above

            # 3. leading whitespace / bad indenting
            if checkBadIndenting:
                leadingWhitespaceRe = re.compile(b"^\s*")
                commentIsOpen = False
                previousLine = b""
                previousIndent = 0
                lineNo = 1
                for line in lines:
                    if commentIsOpen:
                        # don't check leading whitespace inside comments
                        commentIsOpen = multilineCommentIsOpenAtEol(line, commentIsOpen)
                        previousIndent = 0
                    else:
                        m = leadingWhitespaceRe.search(line)
                        indent = m.end() - m.start()
                        if indent != len(line): # ignore whitespace lines, they are considered trailing whitespace
                            if indent % 4 is not 0 and indent != previousIndent:
                                # potential bad indents are not multiples of 4,
                                # and are not indented the same as the previous line
                                s = previousLine
                                if not allowStrangeIndentOnFollowingLine(previousLine) and not allowStrangeIndentOfLine(line):
                                    status.incrementIssueCount("has-bad-indenting")
                                    if verbose or verboseBadIndenting:
                                        print("error: {0}({1}) bad indent: {2}".format(path, lineNo, indent))
                                        print(line)
                        commentIsOpen = multilineCommentIsOpenAtEol(line, commentIsOpen)
                        previousIndent = indent
                    previousLine = line
                    lineNo += 1

            # 4. trailing whitespace
            trailingWhitespaceRe = re.compile(b"\s*$")
            lineNo = 1
            for line in lines:
                m = trailingWhitespaceRe.search(line)
                trailing = m.end() - m.start()
                if trailing > 0:
                    status.incrementIssueCount("has-trailing-whitespace")
                    if verbose:
                        print("error: {0}({1}) trailing whitespace:".format(path, lineNo))
                        print(line)
                lineNo += 1

            # 5. non-ASCII or weird control characters
            badCharactersRe = re.compile(b"[^\t\r\n\x20-\x7E]+")
            lineNo = 1
            for line in lines:
                m = badCharactersRe.search(line)
                if m:
                    bad = m.end() - m.start()
                    if bad > 0:
                        status.incrementIssueCount("has-bad-character")
                        if verbose:
                            print("error: {0}({1}) bad character:".format(path, lineNo))
                            print(line)
                lineNo += 1

            # 6. require EOL at EOF
            if len(data) > 0:
                lastChar = data[-1]
                if lastChar != b"\n"[0]:
                    status.incrementIssueCount("has-no-eol-at-eof")
                    if verbose:
                        lineNo = len(lines)
                        print("error: {0}({1}) no end-of-line at end-of-file".format(path, lineNo))


print("SUMMARY")
print("=======")
issuesFound = False
for s in statusSummary:
    if s.hasIssues():
        issuesFound = True
        print("error: " + str(s.path) + " (" + s.issueSummaryString() + ")")

if issuesFound:
    sys.exit(1)
else:
    print("all good.")
    sys.exit(0)
