# Usage: capture.sh "<title>" "<command>"   -> appends a markdown block with command + real output
cd /Users/shreenath22/Desktop/AI-Modern-L4-training-pt09252026/Project-Shree-Bhargava/bhargava-code
out=$(eval "$2" 2>&1); rc=$?
printf '\n**%s**\n\n```\n$ %s\n%s\n```\n_exit code: %s · run at %s_\n' "$1" "$2" "$out" "$rc" "$(date '+%Y-%m-%d %H:%M:%S')"
