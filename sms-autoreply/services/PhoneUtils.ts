// PhoneUtils.ts
// Utility functions for phone number formatting

export class PhoneUtils {
  /**
   * Format phone number to 10-digit format by removing spaces and +91 prefix
   * @param phoneNumber - Raw phone number from SMS
   * @returns 10-digit phone number string
   */
  static formatPhoneNumber(phoneNumber: string): string {
    if (!phoneNumber) return '';

    // Remove all non-digit characters
    let cleaned = phoneNumber.replace(/\D/g, '');

    // Remove +91 country code if present
    if (cleaned.startsWith('91') && cleaned.length === 12) {
      cleaned = cleaned.substring(2);
    }

    // Ensure 10-digit format
    if (cleaned.length === 10) {
      return cleaned;
    }

    // If length is not 10, return as-is but log warning
    console.warn(`PhoneUtils: Unexpected phone number length: ${cleaned} (length: ${cleaned.length})`);
    return cleaned;
  }

  /**
   * Validate if phone number is in correct 10-digit format
   * @param phoneNumber - Phone number to validate
   * @returns true if valid 10-digit number
   */
  static isValidPhoneNumber(phoneNumber: string): boolean {
    const formatted = this.formatPhoneNumber(phoneNumber);
    return formatted.length === 10 && /^\d{10}$/.test(formatted);
  }

  /**
   * Create formatted message for AI API
   * @param senderPhone - Sender's phone number
   * @param message - Original message content
   * @returns Formatted message for AI API
   */
  static createAIMessage(senderPhone: string, message: string): string {
    const formattedPhone = this.formatPhoneNumber(senderPhone);
    return `from=${formattedPhone}: ${message}`;
  }
}