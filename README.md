# PipeBot (pb)

PipeBot is a command-line interface tool that allows you to interact with Anthropic's Claude AI model using AWS Bedrock. It's designed for expert users working with Linux, AWS, Kubernetes, Helm, and Python.

```ascii
    ____  ________  __________  ____  ______
   / __ \/  _/ __ \/ ____/ __ )/ __ \/_  __/
  / /_/ // // /_/ / __/ / __  / / / / / /
 / ____// // ____/ /___/ /_/ / /_/ / / /
/_/   /___/_/   /_____/_____/\____/ /_/

+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+-+-+
|p|o|w|e|r|e|d| |b|y| |A|n|t|h|r|o|p|i|c|
+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+-+-+
```

## Features

- Interact with Claude AI directly from your command line
- Support for both single-query and interactive conversation modes
- Streaming responses for real-time interaction
- Colorized output for improved readability
- Multi-line input support in interactive mode
- Seamless integration with Unix pipes
- Execute read-only AWS CLI, kubectl, and Helm commands through AI interaction
- Limit on output size to prevent excessive responses

## Prerequisites

- Python 3.6+
- AWS account with Bedrock access
- Boto3 library
- Colored library
- Configured AWS CLI
- Configured kubectl (for Kubernetes-related queries)
- Installed Helm (for Helm-related queries)

## Usage

### Interactive mode

```
echo hi | ./pb
```

In interactive mode:
- Type your query and end it with 'EOF' on a new line to send it to the AI.
- Use Ctrl+C to interrupt the AI's response.
- Use Ctrl+D to end the session.

### Non-interactive mode (single query)

```
git diff | ./pb --non-interactive
```

### Options

- `--non-interactive`: Run in non-interactive mode (exit after first response)

## Examples

1. Get information about EKS clusters:
   ```
   echo "List all clusters EKS" | ./pb
   ```

2. Describe a specific Kubernetes deployment:
   ```
   echo "Describe the nginx deployment in kube-system" | ./pb
   ```

3. List Helm releases:
   ```
   echo "List all Helm releases in kube-system" | ./pb
   ```

## Security Features

- Only read-only operations are allowed for AWS CLI, kubectl, and Helm
- Certain potentially dangerous flags and options are disallowed
- Output size is limited to prevent excessive responses

## License

This project is licensed under the MIT License

## Acknowledgments

- Anthropic for the Claude AI model
- AWS for the Bedrock service
