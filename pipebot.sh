# ~/.bashrc.d/pipebot.sh

# User specific
alias pb='PYTHONPATH="/home/ec2-user/llm/pipebot" python3 /home/ec2-user/llm/pipebot/pipebot/main.py'

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
    command=$(echo "$prompt" | pb --non-interactive --no-memory 2>&1 | grep "git commit -am"| tail -n 1)

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
    echo "$prompt" | pb --non-interactive --no-memory
}

compare() {
    if [ $# -ne 2 ]; then
        echo "Usage: compare <file1> <file2>"
        return 1
    fi

    local file1="$1"
    local file2="$2"
    local file1_content file2_content diff_output prompt

    # Check if files exist
    if [ ! -f "$file1" ] || [ ! -f "$file2" ]; then
        echo "Error: One or both files do not exist."
        return 1
    fi

    # Capture file contents
    file1_content=$(cat "$file1")
    file2_content=$(cat "$file2")

    # Generate diff
    diff_output=$(diff -u "$file1" "$file2")

    # Display contents and diff
    echo "File 1: $file1"
    echo "$file1_content"
    echo "---"
    echo "File 2: $file2"
    echo "$file2_content"
    echo "---"
    echo "Diff:"
    echo "$diff_output"
    echo "---"

    # Prepare prompt for AI
    prompt=$(cat <<EOF
Analyze the following comparison between two files and provide a clear, enriched summary. Do not execute any function calls. Format your response as follows:

1. Overview:
   - Briefly summarize the overall differences between the two files (1-2 sentences)
   - Number of lines changed, added, or removed

2. Detailed Analysis:
   - List the specific changes made, including line numbers when relevant
   - Highlight any significant additions, deletions, or modifications
   - Identify patterns or themes in the changes

3. Impact Assessment:
   - Potential impact of these changes (e.g., on functionality, performance, readability)
   - Any potential issues or points of interest
   - Suggestions for further review or testing

Ensure your analysis is concise yet informative. Use technical language appropriate for experienced developers.

File 1: $file1
$file1_content

File 2: $file2
$file2_content

Diff Output:
$diff_output
EOF
)

    # Generate analysis using AI
    echo "$prompt" | pb --non-interactive --no-memory
}

gitmerge() {
    if [ $# -ne 1 ]; then
        echo "Usage: gitmerge <target_branch>"
        return 1
    fi

    local current_branch target_branch diff_output prompt

    # Get current branch name
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    target_branch="$1"

    # Security check: prevent merging from main
    if [ "$current_branch" = "main" ]; then
        echo "Error: You are currently on 'main' branch. Please checkout the source branch first."
        return 1
    fi

    # Generate diff
    diff_output=$(git diff "$target_branch..$current_branch")

    # Display basic information
    echo "Comparing branches:"
    echo "Source: $current_branch"
    echo "Target: $target_branch"
    echo "---"
    echo "Diff:"
    echo "$diff_output"
    echo "---"

    # Prepare prompt for AI
    prompt=$(cat <<EOF
Analyze the following Git branch comparison and provide a clear, enriched summary. Do not execute any function calls. Format your response as follows:

1. Overview:
   - Briefly summarize the overall differences between the two branches (1-2 sentences)
   - Number of files changed, insertions, and deletions

2. Detailed Analysis:
   - List the files that have been modified, added, or deleted
   - Highlight significant changes in each file
   - Identify patterns or themes in the changes across files

3. Impact Assessment:
   - Potential impact of these changes (e.g., on functionality, performance, readability)
   - Any potential issues or points of interest
   - Suggestions for further review or testing

4. Merge Readiness:
   - Assess whether the changes appear ready to be merged
   - Highlight any conflicts or areas that may need resolution before merging

Ensure your analysis is concise yet informative. Use technical language appropriate for experienced developers.

Source Branch: $current_branch
Target Branch: $target_branch

Diff Output:
$diff_output
EOF
)

    # Generate analysis using AI
    echo "$prompt" | pb --non-interactive --no-memory

    # Propose and execute merge
    read -p "Switch to '$target_branch' and merge '$current_branch'? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git checkout "$target_branch"
        git merge "$current_branch"
        
        # If merge was successful
        if [ $? -eq 0 ]; then
            # Push the merge
            git push
            
            # Propose branch deletion
            read -p "Delete branch $current_branch (local and remote)? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                git branch -d "$current_branch"
                git push origin --delete "$current_branch"
            else
                echo "Branches not deleted."
            fi
        fi
    else
        echo "Merge not executed."
    fi
}
