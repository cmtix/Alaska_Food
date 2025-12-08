## auto_push_data.R
## Push changes under DATA/ to GitHub (retail_food_prices branch)

repo_root <- "C:/Users/vlcollier/GITHUB_PUSH"
data_rel  <- "DATA"  # relative to repo_root

# helper to run git in the correct repo
git_cmd <- function(args) {
  system2("git", c("-C", repo_root, args),
          stdout = TRUE, stderr = TRUE)
}

#--- Safety checks -----------------------------------------------------------

if (!dir.exists(repo_root)) {
  stop("Repo root does not exist: ", repo_root)
}

if (!dir.exists(file.path(repo_root, ".git"))) {
  stop("No .git directory found at repo root. Is this a git repo?")
}

git_ok <- tryCatch(
  {
    system2("git", "--version", stdout = TRUE, stderr = TRUE)
    TRUE
  },
  error = function(e) FALSE
)

if (!git_ok) stop("Git not found on PATH. Install Git or add it to PATH first.")

# Confirm branch
current_branch <- trimws(git_cmd(c("rev-parse", "--abbrev-ref", "HEAD"))[1])

if (!identical(current_branch, "retail_food_prices")) {
  stop("Current branch is '", current_branch,
       "', not 'retail_food_prices'. Aborting.")
}

#--- Check for changes under DATA/ ------------------------------------------

status <- git_cmd(c("status", "--porcelain", "--", data_rel))
status <- status[nzchar(status)]  # drop empty lines

# Ignore the case where ONLY the empty DATA/ dir is untracked
status_effective <- status[status != "?? DATA/"]

if (length(status_effective) == 0) {
  message("No changed files under ", data_rel, " (DATA/ may be empty). Nothing to commit.")
  quit(save = "no")
}

message("Changes detected under ", data_rel, ":")
message(paste(status_effective, collapse = "\n"))

#--- Stage only DATA/ --------------------------------------------------------

message("\nStaging DATA/ ...")
git_cmd(c("add", data_rel))

#--- Commit ------------------------------------------------------------------

timestamp  <- format(Sys.time(), "%Y-%m-%d %H:%M:%S")
commit_msg <- paste0("Update DATA files: ", timestamp)

message("\nCommitting with message: ", commit_msg)

# IMPORTANT: quote the commit message so spaces/colon are safe
commit_out <- git_cmd(c("commit", "-m", shQuote(commit_msg)))
message(paste(commit_out, collapse = "\n"))

#--- Push --------------------------------------------------------------------

message("\nPushing to remote (origin / retail_food_prices)...")
push_out <- git_cmd("push")
message(paste(push_out, collapse = "\n"))

message("\nDone.")


message("\nDone.")
