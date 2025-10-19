a ReAct agent where everything is recorded as an event in a messagedb stream
stream = thread
    thread is like one claude code session
    series of multi-turn user messages, llm responses, tool calls, tool results, etc
    {category}:{version}-{threadId}
each step
    read stream of events for threadId
    events determine what to do next
        usually the last event
        eg last event is UserMessageAdded => call LLM
    fold/reduce/project events into something
        this fold function should be customizable
    provide that something to the next step
    possible steps:
        call LLM, get response
        call tool, get result
        end step
    result of the step is written to stream in event
keep executing steps until done
why use messagedb+events instead of an in-memory list of messages or files?
    in-memory list is lost after process exits
    files are bound to file system of one computer
    database is durable and accessible by multiple processes
    events stored in mdb are not what get sent to LLM
        llm(reduce(events))
        transform the stored events into the messages sent to LLM
        can store way more information than is sent to LLM
        can modify events (eg drop, rewrite) before sending to LLM
        can compact/summarize before sending to LLM
    actual tool call response from LLM not necessarily args for tool call
        tool(reduce(events))
        transform the stored events (that end with LLM's tool call) into the args sent to tool
        tools can have effects (write file, http request0), record tool effects in events
    allows for other steps besides LLM & tools
        not event sure what this would be...
    steps don't have to be executed by same process/computer
        recover after failure
        scale out processing across workers
    events can be processed by other things
        analyze agent/user sessions
        consume event stream, react to certain events (eg notifications, trigger other agents)
how would human-in-the-loop work?
how would streaming partial results work?
trace to langsmith (or any otel?)
