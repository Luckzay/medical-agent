export interface ServerSentEvent {
  data: string;
  event: string;
  id?: string;
  retry?: number;
}

export interface SSEParser {
  feed: (chunk: string) => void;
  end: () => void;
}

/**
 * Incrementally parses an SSE text stream. Chunks may end anywhere, including
 * between CRLF bytes or in the middle of a field/value.
 */
export function createSSEParser(onEvent: (event: ServerSentEvent) => void): SSEParser {
  let buffer = '';
  let eventType = '';
  let eventId: string | undefined;
  let retry: number | undefined;
  let dataLines: string[] = [];

  const dispatch = () => {
    if (!dataLines.length) {
      eventType = '';
      retry = undefined;
      return;
    }
    onEvent({
      data: dataLines.join('\n'),
      event: eventType || 'message',
      ...(eventId === undefined ? {} : { id: eventId }),
      ...(retry === undefined ? {} : { retry }),
    });
    dataLines = [];
    eventType = '';
    retry = undefined;
  };

  const processLine = (line: string) => {
    if (line === '') {
      dispatch();
      return;
    }
    if (line.startsWith(':')) return;

    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    if (field === 'data') dataLines.push(value);
    else if (field === 'event') eventType = value;
    else if (field === 'id' && !value.includes('\0')) eventId = value;
    else if (field === 'retry' && /^\d+$/.test(value)) retry = Number(value);
  };

  const drain = (flush = false) => {
    let start = 0;
    for (let index = 0; index < buffer.length; index += 1) {
      const character = buffer[index];
      if (character !== '\n' && character !== '\r') continue;
      if (character === '\r' && index + 1 === buffer.length && !flush) break;
      processLine(buffer.slice(start, index));
      if (character === '\r' && buffer[index + 1] === '\n') index += 1;
      start = index + 1;
    }
    buffer = buffer.slice(start);
  };

  return {
    feed(chunk) {
      buffer += chunk;
      drain();
    },
    end() {
      drain(true);
      if (buffer) processLine(buffer);
      buffer = '';
      dispatch();
    },
  };
}
