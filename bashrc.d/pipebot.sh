# ~/.bashrc.d/pipebot.sh

# User specific
gitcommit() {
    local git_status git_diff git_diff_cached prompt command

    # Capture Git information
    git_status=$(git status 2>&1)
    git_diff=$(git --no-pager diff 2>&1)
    git_diff_cached=$(git --no-pager diff --cached 2>&1)

    # Display Git status and diffs
    echo "$git_status"
    echo "$git_diff"
    echo "$git_diff_cached"

    # Prepare the prompt for the AI
    prompt=$(cat <<EOF
Based on the following Git information, generate a concise and relevant commit message:

Git Status:
$git_status

Changes in tracked files:
$git_diff

Changes in staged files (including new files):
$git_diff_cached

IMPORTANT: Your response must be a single line starting with 'git commit -am "' and ending with '"' (double quote).
The commit message should be concise, relevant, and describe the changes made.
Do not include any explanation or additional text. Only provide the git commit command.
EOF
)

    # Generate commit command using AI
    command=$(echo "$prompt" | pb --non-interactive | tail -n 1)

    # Propose and execute the command
    if propose_and_execute_command "$command"; then
        propose_and_execute_push
    fi
}

propose_and_execute_command() {
    local command="$1"
    echo "Proposed command: $command"
    read -p "Execute this command? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        eval "$command"
        return 0
    else
        echo "Command not executed."
        return 1
    fi
}

propose_and_execute_push() {
    read -p "Execute git push? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git push
    else
        echo "Push not executed."
    fi
}

gitdiff() {
    local git_diff prompt

    # Capture Git diff
    git_diff=$(git --no-pager diff 2>&1)

    # Prepare the prompt for the AI
    prompt=$(cat <<EOF
Analyze the following git diff output and provide a clear, enriched summary. Do not execute any function calls. Format your response as follows:

1. Overview:
   - Briefly summarize the overall changes (1-2 sentences)
   - Number of files changed
   - Total lines added and removed

2. File-by-File Analysis:
   For each changed file:
   - Filename
   - Type of changes (e.g., modification, addition, deletion)
   - Summary of changes (2-3 bullet points)
   - Any potential issues or points of interest

3. Impact Assessment:
   - Potential impact on the codebase (e.g., performance, functionality, readability)
   - Suggestions for testing or areas to pay attention to

Ensure your analysis is concise yet informative. Use technical language appropriate for experienced developers.

Git Diff Output:
$git_diff
EOF
)

    # Generate analysis using AI
    echo "$prompt" | pb --non-interactive
}
