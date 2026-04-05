# Design Doc: Fix SuperGemini Symlink Portability

## 1. Problem
The file `gemini/supergemini/supergemini` is a symbolic link that points to an absolute path:
`/home/y_ohi/dotfiles/components/dotfiles-ai/gemini/supergemini`
This breaks portability across different machines and environments.

## 2. Proposed Solution
Replace the absolute symbolic link with a relative one.
Specifically, change `gemini/supergemini/supergemini` to point to `.` (the current directory).

### Before
`gemini/supergemini/supergemini -> /home/y_ohi/dotfiles/components/dotfiles-ai/gemini/supergemini`

### After
`gemini/supergemini/supergemini -> .`

## 3. Impact Analysis
- **Imports:** `from gemini.supergemini.supergemini import ...` will still work because the symlink effectively makes `supergemini` a submodule of itself.
- **Tools:** Most Python tools and editors handle self-referential symlinks gracefully, but it's a minimal-impact way to maintain existing structure while ensuring portability.
- **Portability:** The link will work regardless of where the repository is cloned.

## 4. Verification Plan
1.  Verify the symlink points to `.` using `ls -l`.
2.  Confirm no hard-coded `/home/y_ohi/` remains in the link target.
3.  Check that Python can still resolve `gemini.supergemini.supergemini` (if needed).
