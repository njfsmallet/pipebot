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
- Conversation memory management for improved context retention
- Embedding-based retrieval of relevant past interactions

## Prerequisites

- Python 3.6+
- AWS account with Bedrock access
- Boto3 library
- Colored library
- Configured AWS CLI
- Configured kubectl (for Kubernetes-related queries)
- Installed Helm (for Helm-related queries)
- ChromaDB library
- BeautifulSoup4 library (for web search capabilities)

## Installation

1. Clone this repository:
   ```
   git clone <repository_url>
   ```

2. Install the required Python libraries:
   ```
   pip3 install boto3 colored chromadb requests beautifulsoup4 prettytable urllib3
   ```

3. Configure your AWS credentials:
   ```
   aws configure
   ```

## Usage

### Interactive mode

```
echo hi | ./pb
```

or

```
uname -a | ./pb
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

### Memory Management

PipeBot now includes a memory management feature that stores and retrieves relevant parts of past conversations. This allows for improved context retention across multiple interactions.

- Conversations are automatically stored in a local ChromaDB database.
- Relevant past interactions are retrieved based on the similarity to the current query.
- The AI assistant uses this context to provide more informed and consistent responses.

The memory database is stored in `~/.pipebot/memory` by default.

## Configuration

- The script uses the 'default' AWS profile.
- The Claude model is set to "anthropic.claude-3-5-haiku-20241022-v1:0".
- The AWS region is set to 'us-west-2'.
- The conversation memory is stored locally using ChromaDB.
- The embedding model used for memory retrieval is "amazon.titan-embed-text-v2:0".

## AWS CLI Integration

PipeBot can execute read-only AWS CLI commands for allowed services. Supported services include:
acm, autoscaling, cloudformation, cloudfront, cloudtrail, cloudwatch, directconnect, ebs, ec2, ecr, ecs, efs, eks, elb, elbv2, iam, kafka, kms, lambda, logs, rds, route53, s3, secretsmanager, sns, sqs, and ce.

Only commands starting with 'describe', 'get', 'list', 'search', 'lookup-events', or 'filter-log-events' are allowed.

## Kubernetes Integration

PipeBot can execute read-only kubectl commands. Supported kubectl operations include:
- get
- describe
- logs
- top (node, pod)
- version
- api-resources
- explain

Allowed resources for get and describe include: pods, services, deployments, replicasets, nodes, namespaces, configmaps, secrets, persistentvolumes, persistentvolumeclaims, events, ingresses, jobs, cronjobs, roles, rolebindings, clusterroles, clusterrolebindings, serviceaccounts, networkpolicies, crds (customresourcedefinitions), ec2nodeclasses, and nodepools.

## Helm Integration

PipeBot can execute read-only Helm commands. Supported Helm operations include:
- search
- list
- get (all, hooks, manifest, notes, values)
- history
- show (all, chart, readme, values)
- status
- env
- version
- dependency (list, build)
- lint
- template
- verify

## Web Search Integration

PipeBot can perform web searches using Google Search. This feature uses BeautifulSoup4 to parse search results and provides:
- Access to current documentation and technical resources
- Solutions to technical problems
- Up-to-date information about technologies and tools
- Research on best practices and common patterns

Search results are limited to the top 5 most relevant matches to keep responses focused and concise.

## Examples

1. Get information about EC2 instances:
   ```
   echo "List all clusters EKS" | ./pb
   ```

2. Describe a specific Kubernetes deployment:
   ```
   echo "Describe the nginx deployment in kube-system" | ./pb
   ```

3. List Helm releases:
   ```
   echo "List all Helm releases" | ./pb
   ```

4. Search for technical documentation:
   ```
   echo "Find documentation about AWS EKS best practices" | ./pb
   ```

## Security Features

- Only read-only operations are allowed for AWS CLI, kubectl, and Helm
- Certain potentially dangerous flags and options are disallowed
- Output size is limited to prevent excessive responses
- Conversation memory is stored locally, ensuring data privacy

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Anthropic for the Claude AI model
- AWS for the Bedrock service
