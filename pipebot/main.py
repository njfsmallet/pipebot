import sys
from pipebot.cli import CLIParser
from pipebot.logging_utils import Logger
from pipebot.memory.manager import MemoryManager
from pipebot.memory.knowledge_base import KnowledgeBase
from pipebot.ai.assistant import AIAssistant

def print_interaction_info(app_config):
    """Display the welcome banner and usage information."""
    logger = Logger(app_config, False)
    ascii_banner = """
    ____  ________  __________  ____  ______
   / __ \/  _/ __ \/ ____/ __ )/ __ \/_  __/
  / /_/ // // /_/ / __/ / __  / / / / / /
 / ____// // ____/ /___/ /_/ / /_/ / / /
/_/   /___/_/   /_____/_____/\____/ /_/

+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+
|p|o|w|e|r|e|d| |b|y| |B|e|d|r|o|c|k|
+-+-+-+-+-+-+-+ +-+-+ +-+-+-+-+-+-+-+
"""

    print(f"{app_config.colors.green}{ascii_banner}{app_config.colors.reset}")
    logger.info("When interacting, type 'EOF' and hit Enter to finalize your input.")
    logger.info("Use 'Ctrl+c' to halt the AI's ongoing response.")
    logger.info("Press 'Ctrl+d' when you wish to end the session.")

def run_interactive_mode(app_config, assistant, conversation_history):
    """Run the assistant in interactive mode."""
    with open("/dev/tty") as tty:
        sys.stdin = tty
        while True:
            try:
                sys.stdout.write(f"{app_config.colors.blue}>>>{app_config.colors.reset}\n")
                user_input = []
                for line in iter(input, "EOF"):
                    user_input.append(line)
                user = "\n".join(user_input)
                conversation_history.append({"role": "user", "content": [{"text": user}]})
                sys.stdout.write(f"{app_config.colors.blue}<<<{app_config.colors.reset}\n")
                conversation_history = assistant.generate_response(conversation_history)
                sys.stdout.write("\n")
            except EOFError:
                break

def main():
    cli = CLIParser()
    args = cli.parse_args()
    logger = Logger(cli.app_config, args.debug)

    # Handle standalone commands first
    if args.clear:
        try:
            memory_manager = MemoryManager(cli.app_config, debug=args.debug)
            try:
                count = memory_manager.collection.count()
                if count > 0:
                    results = memory_manager.collection.get()
                    memory_manager.collection.delete(ids=results['ids'])
                    logger.success("Conversation memory cleared successfully.")
                else:
                    logger.info("No conversation memory to clear.")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Error clearing memory: {str(e)}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error clearing memory: {str(e)}")
            sys.exit(1)

    if args.scan:
        try:
            kb = KnowledgeBase(cli.app_config, debug=args.debug)
            kb.scan_documents()
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error scanning knowledge base: {str(e)}")
            sys.exit(1)

    if args.status:
        try:
            kb = KnowledgeBase(cli.app_config, debug=args.debug)
            results = kb.collection.get(
                include=['metadatas']
            )
            
            if results and results['metadatas']:
                logger.info(f"Knowledge base contains {len(results['metadatas'])} documents")
                sources = {
                    metadata['source'] 
                    for metadata in results['metadatas'] 
                    if 'source' in metadata
                }
                logger.info("Indexed files:")
                for source in sorted(sources):
                    logger.info(f"  - {source}")
            else:
                logger.info("Knowledge base is empty")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error getting knowledge base status: {str(e)}")
            sys.exit(1)

    # Only check for pipe input if we're not running a standalone command
    cli.check_for_pipe()

    assistant = AIAssistant(cli.app_config, debug=args.debug, use_memory=not args.no_memory)
    
    if not args.non_interactive:
        print_interaction_info(cli.app_config)

    user = sys.stdin.read().strip()
    if not user:
        logger.error("No input provided. Please pipe in some text or use interactive mode.")
        sys.exit(1)

    conversation_history = [
        {"role": "user", "content": user},
    ]

    sys.stdout.write(f"{cli.app_config.colors.blue}>>>{cli.app_config.colors.reset}\n")
    sys.stdout.write(f"{user}\n\n")
    sys.stdout.write(f"{cli.app_config.colors.blue}<<<{cli.app_config.colors.reset}\n")

    assistant.generate_response(conversation_history)

    sys.stdout.write("\n")

    if not args.non_interactive:
        run_interactive_mode(cli.app_config, assistant, conversation_history)

if __name__ == "__main__":
    main() 