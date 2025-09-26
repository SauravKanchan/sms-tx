import { Image } from 'expo-image';
import { StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { useState, useEffect } from 'react';

import { HelloWave } from '@/components/hello-wave';
import ParallaxScrollView from '@/components/parallax-scroll-view';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { smsAutoReplyService, AutoReplyStats } from '@/services/SMSAutoReplyService';
import { BackgroundTaskService } from '@/services/BackgroundTaskService';
import { modernBackgroundService } from '@/services/ModernBackgroundService';
import { debugLogger } from '@/services/DebugLogger';
import { DebugLogViewer } from '@/components/DebugLogViewer';

export default function HomeScreen() {
  const [stats, setStats] = useState<AutoReplyStats>({
    messagesReceived: 0,
    messagesReplied: 0,
    errors: 0,
    isActive: false
  });

  useEffect(() => {
    const currentStats = smsAutoReplyService.getStats();
    setStats(currentStats);

    // Log app initialization
    debugLogger.info('SYSTEM', 'SMS Auto-Reply app initialized');
  }, []);

  const handleStartService = async () => {
    try {
      debugLogger.info('SYSTEM', 'User requested to start SMS Auto-Reply service');
      const success = await smsAutoReplyService.start(setStats);
      if (success) {
        Alert.alert('Success', 'SMS Auto-Reply service started successfully!');
        debugLogger.info('BACKGROUND', 'Starting background services...');
        await BackgroundTaskService.start();
        await modernBackgroundService.startBackgroundProcessing();
        debugLogger.success('BACKGROUND', 'Background services started');
      } else {
        Alert.alert('Error', 'Failed to start SMS Auto-Reply service. Please check permissions.');
      }
    } catch (error) {
      debugLogger.error('SYSTEM', 'Failed to start service from UI', error);
      Alert.alert('Error', `Failed to start service: ${error}`);
    }
  };

  const handleStopService = () => {
    debugLogger.info('SYSTEM', 'User requested to stop SMS Auto-Reply service');
    smsAutoReplyService.stop();
    debugLogger.info('BACKGROUND', 'Stopping background services...');
    BackgroundTaskService.stop();
    modernBackgroundService.stopBackgroundProcessing();
    debugLogger.success('BACKGROUND', 'Background services stopped');
    Alert.alert('Stopped', 'SMS Auto-Reply service has been stopped.');
  };

  const handleResetStats = () => {
    debugLogger.info('SYSTEM', 'User requested to reset statistics');
    smsAutoReplyService.resetStats();
    setStats(smsAutoReplyService.getStats());
    Alert.alert('Reset', 'Statistics have been reset.');
  };

  return (
    <ParallaxScrollView
      headerBackgroundColor={{ light: '#A1CEDC', dark: '#1D3D47' }}
      headerImage={
        <Image
          source={require('@/assets/images/partial-react-logo.png')}
          style={styles.reactLogo}
        />
      }>
      <ThemedView style={styles.titleContainer}>
        <ThemedText type="title">SMS Auto-Reply</ThemedText>
        <HelloWave />
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Service Status</ThemedText>
        <ThemedView style={styles.statusContainer}>
          <ThemedText style={[styles.statusText, { color: stats.isActive ? 'green' : 'red' }]}>
            {stats.isActive ? '🟢 Active' : '🔴 Inactive'}
          </ThemedText>
        </ThemedView>
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Statistics</ThemedText>
        <ThemedView style={styles.statsContainer}>
          <ThemedText>📥 Messages Received: {stats.messagesReceived}</ThemedText>
          <ThemedText>📤 Messages Replied: {stats.messagesReplied}</ThemedText>
          <ThemedText>❌ Errors: {stats.errors}</ThemedText>
        </ThemedView>
        {stats.lastMessage && (
          <ThemedView style={styles.lastMessageContainer}>
            <ThemedText type="defaultSemiBold">Last Message:</ThemedText>
            <ThemedText>From: {stats.lastMessage.address}</ThemedText>
            <ThemedText>Message: {stats.lastMessage.body}</ThemedText>
            <ThemedText>Time: {new Date(stats.lastMessage.date).toLocaleString()}</ThemedText>
          </ThemedView>
        )}
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Controls</ThemedText>
        <ThemedView style={styles.controlsContainer}>
          {!stats.isActive ? (
            <TouchableOpacity style={styles.startButton} onPress={handleStartService}>
              <ThemedText style={styles.buttonText}>Start Auto-Reply Service</ThemedText>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={styles.stopButton} onPress={handleStopService}>
              <ThemedText style={styles.buttonText}>Stop Auto-Reply Service</ThemedText>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.resetButton} onPress={handleResetStats}>
            <ThemedText style={styles.buttonText}>Reset Statistics</ThemedText>
          </TouchableOpacity>
        </ThemedView>
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">How It Works</ThemedText>
        <ThemedText>
          This app automatically listens for incoming SMS messages and sends pre-configured responses.
          Make sure to test on a physical Android device with proper SMS permissions.
        </ThemedText>
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <ThemedText type="subtitle">Important Notes</ThemedText>
        <ThemedText>
          • Requires SMS permissions on Android{'\n'}
          • Must be tested on physical device{'\n'}
          • Background processing keeps service running{'\n'}
          • Uses hardcoded responses (API integration ready)
        </ThemedText>
      </ThemedView>

      <ThemedView style={styles.stepContainer}>
        <DebugLogViewer maxHeight={400} />
      </ThemedView>
    </ParallaxScrollView>
  );
}

const styles = StyleSheet.create({
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stepContainer: {
    gap: 8,
    marginBottom: 16,
  },
  statusContainer: {
    padding: 12,
    borderRadius: 8,
    backgroundColor: 'rgba(0,0,0,0.05)',
  },
  statusText: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  statsContainer: {
    padding: 12,
    borderRadius: 8,
    backgroundColor: 'rgba(0,0,0,0.05)',
    gap: 4,
  },
  lastMessageContainer: {
    padding: 12,
    borderRadius: 8,
    backgroundColor: 'rgba(0,0,0,0.1)',
    marginTop: 8,
    gap: 4,
  },
  controlsContainer: {
    gap: 12,
  },
  startButton: {
    backgroundColor: '#4CAF50',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
  },
  stopButton: {
    backgroundColor: '#F44336',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
  },
  resetButton: {
    backgroundColor: '#FF9800',
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
  },
  buttonText: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
  },
  reactLogo: {
    height: 178,
    width: 290,
    bottom: 0,
    left: 0,
    position: 'absolute',
  },
});
