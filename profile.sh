#!/usr/bin/env bash
set -euo pipefail

build_dir="${1:-build}"
output_dir="${2:-${build_dir}/profiling}"

mkdir -p "$output_dir"

order_book_bench="${build_dir}/engine/bench/bench_order_book"
matching_bench="${build_dir}/engine/bench/bench_matching"

if command -v perf >/dev/null 2>&1; then
  perf stat -o "$output_dir/perf-stat.txt" -- "$order_book_bench" || true
fi

if command -v valgrind >/dev/null 2>&1; then
  valgrind --tool=memcheck --log-file="$output_dir/valgrind-memcheck.txt" "$matching_bench" || true
  valgrind --tool=cachegrind --cachegrind-out-file="$output_dir/cachegrind.out" "$order_book_bench" || true
fi

echo "Reports written to $output_dir"