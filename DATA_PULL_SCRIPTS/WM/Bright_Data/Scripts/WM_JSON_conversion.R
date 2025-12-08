# 
# 
# # --- Packages ---
# library(jsonlite)
# library(ndjson)
# library(dplyr)
# library(tidyr)
# library(purrr)
# library(tibble)
# library(stringr)
# 
# # ---------- Reader that auto-detects JSON array vs NDJSON ----------
# 
# 
# 
# read_walmart_json <- function(path) {
#   first_line <- readLines(path, n = 1, warn = FALSE)
#   if (grepl("^\\s*\\[", first_line)) {
#     message("Reading as JSON array with jsonlite::fromJSON(): ", basename(path))
#     out <- jsonlite::fromJSON(path, flatten = TRUE)
#   } else {
#     message("Reading as NDJSON with ndjson::stream_in(): ", basename(path))
#     con <- file(path, "r")
#     on.exit(close(con), add = TRUE)
#     out <- ndjson::stream_in(con, flatten = TRUE, verbose = FALSE)
#   }
#   as_tibble(out)
# }
# 
# # ---------- Pull all matching files and merge into one tibble ----------
# # dir: folder path
# # pattern: regex for files to include (default: *.json or *.json.gz)
# # recursive: whether to search subfolders
# read_walmart_dir <- function(dir,
#                              pattern   = "\\.json(\\.gz)?$",
#                              recursive = FALSE) {
#   
#   files <- list.files(dir, pattern = pattern, full.names = TRUE,
#                       recursive = recursive, ignore.case = TRUE)
#   
#   if (!length(files)) {
#     stop("No files found in: ", dir,
#          " matching pattern: ", pattern, call. = FALSE)
#   }
#   
#   # Safe reader so one bad file doesn't kill the run
#   safe_read <- purrr::safely(function(f) {
#     read_walmart_json(f) %>%
#       mutate(source_file = basename(f), .before = 1)
#   }, otherwise = NULL)
#   
#   results <- purrr::map(files, safe_read)
#   
#   # Separate successes and failures
#   dfs <- results |> purrr::map("result") |> purrr::compact()
#   errs <- results |> purrr::map("error")
#   
#   if (any(!vapply(errs, is.null, logical(1)))) {
#     bad <- files[!vapply(errs, is.null, logical(1))]
#     warning("Skipped unreadable files:\n  - ", paste(bad, collapse = "\n  - "))
#   }
#   
#   if (!length(dfs)) stop("All file reads failed.", call. = FALSE)
#   
#   # Keep only shared columns across all files to ensure clean bind
#   common_cols <- Reduce(intersect, lapply(dfs, names))
#   
#   # Fuzzy match for flexible inclusion colnames----
#   inclusion_words <- c("title","description","zip","price","location","city")
#   regex <- paste(inclusion_words, collapse = "|")
#   select(matches(regex, ignore.case = TRUE))
#   
#   out <- dfs |>
#     map(~ dplyr::select(.x, dplyr::all_of(common_cols))) |>
#     dplyr::bind_rows() %>%
#     unnest_longer(search_results) %>%
#     unnest_wider(search_results)%>%
#     unnest_longer(facets)%>%
#     unnest_wider(facets)%>%
#     paste(inclusion_words, collapse = "|")%>%
#     select(matches(regex, ignore.case = TRUE))
#   
#   
#   
#   # Optional: de-duplicate identical rows
#   out <- dplyr::distinct(out)
#   
#   out
# }
# 
# # --------- USE IT ----------
# dir_path <- "G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/UAV Rural Essential Goods Delivery/FOOD_PRICING/Data_Scraping/Walmart/25_08"
# 
#   
# walmart <- read_walmart_dir(dir_path, pattern = "\\.json$" )
# 
# # Inspect
# glimpse(walmart)

# REVISION 2

# --- Packages ---
library(jsonlite)
library(ndjson)
library(dplyr)
library(tidyr)
library(purrr)
library(tibble)
library(stringr)

read_walmart_json <- function(path) {
  first_line <- readLines(path, n = 1, warn = FALSE)
  if (grepl("^\\s*\\[", first_line)) {
    message("Reading as JSON array with jsonlite::fromJSON(): ", basename(path))
    out <- jsonlite::fromJSON(path, flatten = TRUE)
  } else {
    message("Reading as NDJSON with ndjson::stream_in(): ", basename(path))
    con <- file(path, "r")
    on.exit(close(con), add = TRUE)
    out <- ndjson::stream_in(con, flatten = TRUE, verbose = FALSE)
  }
  as_tibble(out)
}

read_walmart_dir <- function(dir,
                             pattern   = "\\.json(\\.gz)?$",
                             recursive = FALSE) {
  
  files <- list.files(dir, pattern = pattern, full.names = TRUE,
                      recursive = recursive, ignore.case = TRUE)
  
  if (!length(files)) {
    stop("No files found in: ", dir,
         " matching pattern: ", pattern, call. = FALSE)
  }
  
  # Safe reader so one bad file doesn't kill the run
  safe_read <- purrr::safely(function(f) {
    read_walmart_json(f) %>%
      mutate(source_file = basename(f), .before = 1)
  }, otherwise = NULL)
  
  results <- purrr::map(files, safe_read)
  
  dfs  <- results |> purrr::map("result") |> purrr::compact()
  errs <- results |> purrr::map("error")
  
  if (any(!vapply(errs, is.null, logical(1)))) {
    bad <- files[!vapply(errs, is.null, logical(1))]
    warning("Skipped unreadable files:\n  - ", paste(bad, collapse = "\n  - "))
  }
  
  if (!length(dfs)) stop("All file reads failed.", call. = FALSE)
  
  # Bind only shared columns to avoid bind errors
  common_cols <- Reduce(intersect, lapply(dfs, names))
  
  out <- dfs |>
    map(~ dplyr::select(.x, dplyr::all_of(common_cols))) |>
    dplyr::bind_rows()
  
  # If Bright Data put products under a nested list column like `search_results`,
  # unnest it safely (only if present).
  if ("search_results" %in% names(out)) {
    out <- out |>
      tidyr::unnest_longer(search_results, keep_empty = TRUE) |>
      tidyr::unnest_wider(search_results, names_sep = "_", simplify = TRUE)
  }
  
  # If there are other predictable nests (e.g., `facets`), you can unnest similarly:
  if ("facets" %in% names(out) && is.list(out$facets)) {
    out <- out |>
      tidyr::unnest_longer(facets, keep_empty = TRUE) |>
      tidyr::unnest_wider(facets, names_sep = "_", simplify = TRUE)
  }
  
  # Now do the regex-based column keep INSIDE a select()
  inclusion_words <- c("product.title","name","description","Zip_Code",
                       "primary.price","location","address","city","state","store",
                       "upc","itemId","product_id")
  regex <- paste(inclusion_words, collapse = "|")
  
  # with EITHER of these:
  keepable <- names(out)[stringr::str_detect(names(out), stringr::regex(regex, ignore_case = TRUE))]
  if (length(keepable)) {
    out <- dplyr::select(out, dplyr::all_of(keepable))
  } # else keep everything (no-op) if nothing matches
  
  out <- dplyr::distinct(out)
  
  out <- dplyr::mutate(out, PULL_DATE = format(as.Date("08-22-2025", format = "%m-%d-%Y"), "%m-%d-%Y"))
}

# --------- USE IT ----------

# NOTE: THIS IS JUST FOR AUGUST 2025 conversion; future versions have this conversion code included in Python
dir_path <- "G:/.shortcut-targets-by-id/10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg/Drones_MV/UAV Rural Essential Goods Delivery/FOOD_PRICING/Data_Scraping/Walmart/25_08/"
walmart <- read_walmart_dir(dir_path, pattern = "\\.json$")


# Write to csv
dir_path <- paste0(dir_path,"Walmart_08_25.csv")
write.csv(walmart,dir_path)

# Check it
walmart_check <- read.csv(dir_path)


