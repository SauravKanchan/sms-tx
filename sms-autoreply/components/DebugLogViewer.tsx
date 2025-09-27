import React, { useState, useEffect } from 'react';
import { ScrollView, StyleSheet, TouchableOpacity, View } from 'react-native';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { debugLogger, LogEntry } from '@/services/DebugLogger';

interface DebugLogViewerProps {
  maxHeight?: number;
}

export function DebugLogViewer({ maxHeight = 300 }: DebugLogViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    const unsubscribe = debugLogger.subscribe(setLogs);
    return unsubscribe;
  }, []);

  const formatTime = (timestamp: Date): string => {
    return timestamp.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      fractionalSecondDigits: 3
    });
  };

  const getLevelColor = (level: LogEntry['level']): string => {
    switch (level) {
      case 'error': return '#FF5722';
      case 'warning': return '#FF9800';
      case 'success': return '#4CAF50';
      default: return '#2196F3';
    }
  };

  const getCategoryIcon = (category: LogEntry['category']): string => {
    switch (category) {
      case 'SMS_RECEIVE': return '📥';
      case 'SMS_SEND': return '📤';
      case 'BACKGROUND': return '⚙️';
      case 'PERMISSION': return '🔐';
      case 'SYSTEM': return '💻';
      default: return '📝';
    }
  };

  const handleClearLogs = () => {
    debugLogger.clearLogs();
  };

  const displayLogs = isExpanded ? logs : logs.slice(0, 5);

  return (
    <ThemedView style={styles.container}>
      <View style={styles.header}>
        <ThemedText type="subtitle">Debug Logs ({logs.length})</ThemedText>
        <View style={styles.headerButtons}>
          <TouchableOpacity
            style={styles.expandButton}
            onPress={() => setIsExpanded(!isExpanded)}
          >
            <ThemedText style={styles.buttonText}>
              {isExpanded ? 'Collapse' : 'Expand'}
            </ThemedText>
          </TouchableOpacity>
          <TouchableOpacity style={styles.clearButton} onPress={handleClearLogs}>
            <ThemedText style={styles.buttonText}>Clear</ThemedText>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={[styles.logContainer, { maxHeight: isExpanded ? maxHeight : 200 }]}
        showsVerticalScrollIndicator={true}
        nestedScrollEnabled={true}
      >
        {displayLogs.length === 0 ? (
          <ThemedView style={styles.emptyState}>
            <ThemedText style={styles.emptyText}>No logs yet</ThemedText>
          </ThemedView>
        ) : (
          displayLogs.map((log) => (
            <ThemedView key={log.id} style={styles.logEntry}>
              <View style={styles.logHeader}>
                <ThemedText style={styles.timestamp}>
                  {formatTime(log.timestamp)}
                </ThemedText>
                <View style={styles.logMeta}>
                  <ThemedText style={styles.category}>
                    {getCategoryIcon(log.category)} {log.category}
                  </ThemedText>
                  <ThemedText
                    style={[styles.level, { color: getLevelColor(log.level) }]}
                  >
                    {log.level.toUpperCase()}
                  </ThemedText>
                </View>
              </View>
              <ThemedText style={styles.message}>{log.message}</ThemedText>
              {log.data && (
                <ThemedText style={styles.data}>
                  Data: {typeof log.data === 'string' ? log.data : JSON.stringify(log.data, null, 2)}
                </ThemedText>
              )}
            </ThemedView>
          ))
        )}

        {!isExpanded && logs.length > 5 && (
          <TouchableOpacity
            style={styles.showMoreButton}
            onPress={() => setIsExpanded(true)}
          >
            <ThemedText style={styles.showMoreText}>
              ... and {logs.length - 5} more logs (tap to expand)
            </ThemedText>
          </TouchableOpacity>
        )}
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 8,
    backgroundColor: 'rgba(0,0,0,0.05)',
    marginBottom: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.1)',
  },
  headerButtons: {
    flexDirection: 'row',
    gap: 8,
  },
  expandButton: {
    backgroundColor: '#2196F3',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  clearButton: {
    backgroundColor: '#FF5722',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
  },
  buttonText: {
    color: 'white',
    fontSize: 12,
    fontWeight: 'bold',
  },
  logContainer: {
    maxHeight: 300,
  },
  emptyState: {
    padding: 20,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 14,
    opacity: 0.6,
  },
  logEntry: {
    padding: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.05)',
  },
  logHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  timestamp: {
    fontSize: 11,
    opacity: 0.7,
    fontFamily: 'monospace',
  },
  logMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  category: {
    fontSize: 10,
    fontWeight: 'bold',
    opacity: 0.8,
  },
  level: {
    fontSize: 9,
    fontWeight: 'bold',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.8)',
  },
  message: {
    fontSize: 12,
    lineHeight: 16,
  },
  data: {
    fontSize: 10,
    opacity: 0.7,
    marginTop: 4,
    fontFamily: 'monospace',
    backgroundColor: 'rgba(0,0,0,0.05)',
    padding: 4,
    borderRadius: 2,
  },
  showMoreButton: {
    padding: 8,
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.05)',
  },
  showMoreText: {
    fontSize: 12,
    opacity: 0.7,
    fontStyle: 'italic',
  },
});