// PhoneUtils.ts
// Utility functions for phone number formatting

import { debugLogger } from './DebugLogger';

export interface PhoneValidationResult {
  isValid: boolean;
  formattedNumber?: string;
  error?: string;
}

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
   * Comprehensive phone number validation with detailed error reporting
   * @param phoneNumber - Raw phone number to validate
   * @param fieldName - Field name for debugging (e.g., 'from', 'to')
   * @returns Validation result with formatted number or error details
   */
  static validateAndFormatPhone(phoneNumber: string, fieldName: string = 'phone'): PhoneValidationResult {
    if (!phoneNumber) {
      const error = `${fieldName} phone number is required`;
      debugLogger.warning('PHONE_VALIDATION', error);
      return { isValid: false, error };
    }

    if (typeof phoneNumber !== 'string') {
      const error = `${fieldName} phone number must be a string`;
      debugLogger.warning('PHONE_VALIDATION', error);
      return { isValid: false, error };
    }

    // Remove all whitespace and non-digit characters
    let cleaned = phoneNumber.trim().replace(/\D/g, '');

    if (!cleaned) {
      const error = `${fieldName} phone number contains no digits`;
      debugLogger.warning('PHONE_VALIDATION', error, { original: phoneNumber });
      return { isValid: false, error };
    }

    // Remove +91 country code if present
    if (cleaned.startsWith('91') && cleaned.length === 12) {
      cleaned = cleaned.substring(2);
      debugLogger.info('PHONE_VALIDATION', `Removed +91 prefix from ${fieldName}`, {
        original: phoneNumber,
        cleaned
      });
    }

    // Validate exactly 10 digits
    if (cleaned.length !== 10) {
      const error = `${fieldName} phone number must be exactly 10 digits, got ${cleaned.length}`;
      debugLogger.warning('PHONE_VALIDATION', error, {
        original: phoneNumber,
        cleaned,
        length: cleaned.length
      });
      return { isValid: false, error };
    }

    // Validate all characters are digits
    if (!/^\d{10}$/.test(cleaned)) {
      const error = `${fieldName} phone number must contain only digits`;
      debugLogger.warning('PHONE_VALIDATION', error, {
        original: phoneNumber,
        cleaned
      });
      return { isValid: false, error };
    }

    // Additional validation for Indian mobile numbers (should start with 6-9)
    if (!/^[6-9]/.test(cleaned)) {
      const error = `${fieldName} phone number should start with 6, 7, 8, or 9`;
      debugLogger.warning('PHONE_VALIDATION', error, {
        original: phoneNumber,
        cleaned
      });
      return { isValid: false, error };
    }

    debugLogger.info('PHONE_VALIDATION', `Valid ${fieldName} phone number`, {
      original: phoneNumber,
      formatted: cleaned
    });

    return { isValid: true, formattedNumber: cleaned };
  }

  /**
   * Validate transaction phone numbers (both from and to)
   * @param fromPhone - Sender phone number
   * @param toPhone - Recipient phone number
   * @returns Validation result with formatted numbers or errors
   */
  static validateTransactionPhones(fromPhone: string, toPhone: string): {
    isValid: boolean;
    formattedFrom?: string;
    formattedTo?: string;
    errors: string[];
  } {
    const errors: string[] = [];
    let formattedFrom: string | undefined;
    let formattedTo: string | undefined;

    // Validate from phone
    const fromResult = this.validateAndFormatPhone(fromPhone, 'from');
    if (!fromResult.isValid) {
      errors.push(fromResult.error!);
    } else {
      formattedFrom = fromResult.formattedNumber;
    }

    // Validate to phone
    const toResult = this.validateAndFormatPhone(toPhone, 'to');
    if (!toResult.isValid) {
      errors.push(toResult.error!);
    } else {
      formattedTo = toResult.formattedNumber;
    }

    // Check if from and to are the same
    if (formattedFrom && formattedTo && formattedFrom === formattedTo) {
      const error = 'Sender and recipient phone numbers cannot be the same';
      errors.push(error);
      debugLogger.warning('PHONE_VALIDATION', error, {
        from: fromPhone,
        to: toPhone,
        formatted: formattedFrom
      });
    }

    const isValid = errors.length === 0;

    if (isValid) {
      debugLogger.success('PHONE_VALIDATION', 'Transaction phone validation successful', {
        fromOriginal: fromPhone,
        toOriginal: toPhone,
        fromFormatted: formattedFrom,
        toFormatted: formattedTo
      });
    } else {
      debugLogger.error('PHONE_VALIDATION', 'Transaction phone validation failed', {
        fromOriginal: fromPhone,
        toOriginal: toPhone,
        errors
      });
    }

    return {
      isValid,
      formattedFrom,
      formattedTo,
      errors
    };
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