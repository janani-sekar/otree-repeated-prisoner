# === Load libraries ===
library(jsonlite)
library(arrow)
library(tidyverse)
library(ggplot2)

# === Load and preprocess data ===
paired_df <- read_feather("data/player_pair_sequences.feather") %>%
  mutate(
    decision_tuple = map(decision_tuple, ~ map(fromJSON(.x, simplifyVector = FALSE), unlist)),
    payoff_tuple   = map(payoff_tuple,   ~ map(fromJSON(.x, simplifyVector = FALSE), unlist)),
    timeout_occured = map(timeout_tuple, ~ map(fromJSON(.x, simplifyVector = FALSE), unlist))
  )

# === Filter to rows where no timeouts occurred in any round ===
paired_df <- paired_df %>%
  filter(
    map_lgl(timeout_occured, ~ all(flatten_int(.x) == 0))
  )


if (!dir.exists("figures")) dir.create("figures")

# === Compute delta metrics ===
paired_df <- paired_df %>%
  mutate(
    R = group.game_payoff_cooperate_cooperate,
    S = group.game_payoff_betrayed,
    T = group.game_payoff_betray,
    P = group.game_payoff_both_defect,
    g = ((T - P) / (R - P)) - 1,
    l = -1 * ((S - P) / (R - P)),
    delta_spe = g / (1 + g),
    delta_rd  = (g + l) / (1 + g + l),
    Delta_rd  = group.delta_value - delta_rd
  )

# === Histogram of deltas ===
parsed_labels <- c(
  delta      = "delta",
  delta_spe  = "delta[\"spe\"]",
  delta_rd   = "delta[\"rd\"]",
  Delta_rd   = "Delta[\"rd\"]"
)
fill_colors <- c(
  delta      = "red",
  delta_spe  = "blue",
  delta_rd   = "green",
  Delta_rd   = "purple"
)

paired_df %>%
  select(delta_spe, delta_rd, delta = group.delta_value, Delta_rd) %>%
  pivot_longer(everything(), names_to = "measure", values_to = "value") %>%
  mutate(measure = factor(measure, levels = names(parsed_labels))) %>%
  ggplot(aes(x = value, fill = measure)) +
  geom_histogram(bins = 20, color = "black", alpha = 0.5) +
  facet_wrap(~ measure, scales = "free", labeller = as_labeller(parsed_labels, label_parsed)) +
  scale_fill_manual(values = fill_colors) +
  labs(x = NULL, y = "Count", title = "Distribution of δ (and Related Game Metadata)") +
  theme_bw() +
  theme(legend.position = "none")

ggsave("figures/histograms_deltas.png", width = 10, height = 6)

# === Histogram of g and l  ===
gl_hist_df <- paired_df %>%
  select(g, l) %>%
  pivot_longer(cols = everything(), names_to = "component", values_to = "value") %>%
  mutate(component = factor(component, levels = c("g", "l")))

# Compute global bin breaks
bin_width <- 0.5
x_min <- floor(min(gl_hist_df$value, na.rm = TRUE) / bin_width) * bin_width
x_max <- ceiling(max(gl_hist_df$value, na.rm = TRUE) / bin_width) * bin_width
breaks_seq <- seq(x_min, x_max, by = bin_width)

ggplot(gl_hist_df, aes(x = value, fill = component)) +
  geom_histogram(
    breaks = breaks_seq,
    color = "black",
    alpha = 0.5,
    boundary = 0
  ) +
  facet_wrap(~ component, labeller = label_parsed) +
  labs(
    x = NULL,
    y = "Count",
    title = "Distribution of g and l"
  ) +
  theme_bw() +
  theme(legend.position = "none")

# Display and save
ggsave("figures/histogram_gl.png", width = 10, height = 4)


# === Player 1 cooperation metrics ===
paired_df <- paired_df %>%
  mutate(
    p1_coop_rate = map_dbl(decision_tuple, ~ mean(map_dbl(.x, 1))),
    p1_r1_coop   = map_int(decision_tuple, ~ .x[[1]][1])
  )

# === Binned cooperation rates by delta variant ===
delta_vals <- paired_df %>%
  filter(!is.na(group.delta_value)) %>%
  group_by(delta = group.delta_value) %>%
  summarise(
    bin_center = mean(delta),
    coop_rate  = mean(p1_coop_rate),
    r1_coop    = mean(p1_r1_coop),
    measure = "delta",
    .groups = "drop"
  )

other_binned <- paired_df %>%
  select(p1_coop_rate, p1_r1_coop, delta_spe, delta_rd, Delta_rd) %>%
  pivot_longer(c(delta_spe, delta_rd, Delta_rd), names_to = "measure", values_to = "x") %>%
  group_by(measure) %>%
  mutate(bin = ntile(x, 10)) %>%
  group_by(measure, bin) %>%
  summarise(
    bin_center = mean(x),
    coop_rate  = mean(p1_coop_rate),
    r1_coop    = mean(p1_r1_coop),
    .groups = "drop"
  )

binned_df <- bind_rows(delta_vals, other_binned) %>%
  mutate(measure = factor(measure, levels = names(parsed_labels)))

# === Plot binned cooperation rates ===
ggplot(binned_df, aes(x = bin_center, y = coop_rate, color = measure)) +
  geom_point(size = 2) +
  facet_wrap(~ measure, scales = "free_x", labeller = as_labeller(parsed_labels, label_parsed)) +
  scale_color_manual(values = fill_colors) +
  labs(x = NULL, y = "P1 Cooperation Rate", title = "P1 Cooperation Rate by δ (and Related Game Metadata)") +
  theme_bw() +
  theme(legend.position = "none")

ggsave("figures/p1_coop_rate_binned.png", width = 10, height = 6)

ggplot(binned_df, aes(x = bin_center, y = r1_coop, color = measure)) +
  geom_point(size = 2) +
  facet_wrap(~ measure, scales = "free_x", labeller = as_labeller(parsed_labels, label_parsed)) +
  scale_color_manual(values = fill_colors) +
  labs(x = NULL, y = "P1 Round 1 Cooperation", title = "P1 First-Round Cooperation by δ (and Related Game Metadata)") +
  theme_bw() +
  theme(legend.position = "none")

ggsave("figures/p1_r1_coop_binned.png",width = 10, height = 6)

# === Surplus on the table ===
paired_df <- paired_df %>%
  mutate(
    alternate_better    = (T + S) > (2 * R),
    num_rounds          = map_int(payoff_tuple, length),
    max_per_round       = if_else(alternate_better, T + S, 2 * R),
    max_total_payoff    = max_per_round * num_rounds,
    actual_total_payoff = map_dbl(payoff_tuple, ~ sum(map_dbl(.x, sum))),
    surplus_left        = max_total_payoff - actual_total_payoff
  )

ggplot(paired_df, aes(surplus_left)) + 
  geom_histogram(bins = 20, fill = "blue", color = "black", alpha = 0.5) + 
  labs(title = "Distribution of Payoff Surplus Left on the Table", x = "Surplus", y = "Count") +
  theme_bw()

ggsave("figures/surplus_histogram.png", width = 8, height = 4)

# === Memory-1 Histories ===
extract_history <- function(seq) {
  if (length(seq) < 1) return(tibble(previous_pair = character(), next_pair = character(), next_p1 = integer()))
  
  history <- tibble(
    previous_pair = "initial",
    next_pair = paste0(seq[[1]], collapse = ""),
    next_p1 = seq[[1]][1]
  )
  
  if (length(seq) >= 2) {
    after <- tibble(
      previous_pair = map_chr(seq[-length(seq)], ~ paste0(.x, collapse = "")),
      next_pair     = map_chr(seq[-1], ~ paste0(.x, collapse = "")),
      next_p1       = map_int(seq[-1], ~ .x[1])
    )
    history <- bind_rows(history, after)
  }
  return(history)
}

history_df <- paired_df %>%
  mutate(transitions = map(decision_tuple, extract_history)) %>%
  unnest(transitions)

# Summarize both-coop and p1-coop rates
label_binary_pair <- function(pair) {
  recode(pair,
         "11" = "CC", "10" = "CD", "01" = "DC", "00" = "DD",
         "initial" = "initial", .default = pair)
}

history_both_summary <- history_df %>%
  group_by(previous_pair) %>%
  summarise(N = n(), share_both_coop = mean(next_pair == "11"), .groups = "drop") %>%
  bind_rows(
    tibble(previous_pair = "Total", N = nrow(history_df), share_both_coop = mean(history_df$next_pair == "11"))
  ) %>%
  mutate(previous_pair = label_binary_pair(previous_pair)) %>%
  arrange(factor(previous_pair, levels = c("CC", "CD", "DC", "DD", "initial", "Total"))) %>%
  mutate(share_both_coop = sprintf("%.1f%%", share_both_coop * 100), N = scales::comma(N))

history_p1_summary <- history_df %>%
  group_by(previous_pair) %>%
  summarise(N = n(), share_p1_coop = mean(next_p1), .groups = "drop") %>%
  bind_rows(
    tibble(previous_pair = "Total", N = nrow(history_df), share_p1_coop = mean(history_df$next_p1))
  ) %>%
  mutate(previous_pair = label_binary_pair(previous_pair)) %>%
  arrange(factor(previous_pair, levels = c("CC", "CD", "DC", "DD", "initial", "Total"))) %>%
  mutate(share_p1_coop = sprintf("%.1f%%", share_p1_coop * 100), N = scales::comma(N))

# === Regressions and visualization ===
p1_coop_rate_model <- lm(p1_coop_rate ~ Delta_rd, data = paired_df)
summary(p1_coop_rate_model)

p1_r1_coop_model <- lm(p1_r1_coop ~ Delta_rd, data = paired_df)
summary(p1_r1_coop_model)

paired_df %>%
  select(Delta_rd, p1_coop_rate, p1_r1_coop) %>%
  pivot_longer(c(p1_coop_rate, p1_r1_coop), names_to = "outcome", values_to = "value") %>%
  ggplot(aes(x = Delta_rd, y = value)) +
  geom_jitter(alpha = 0.3, height = 0.05, width = 0, size = 0.8) +
  geom_smooth(method = "lm", color = "purple") +
  facet_wrap(~ outcome, scales = "free_y", labeller = as_labeller(c(
    p1_coop_rate = "Overall Coop Rate",
    p1_r1_coop = "First-Round Coop (0/1)"
  ))) +
  labs(
    x = expression(delta[RD]),
    y = NULL,
    title = expression("Cooperation Outcomes vs. " * Delta["rd"])
  ) +
  theme_bw()

ggsave("figures/regression_outcomes.png", width = 10, height = 6)
