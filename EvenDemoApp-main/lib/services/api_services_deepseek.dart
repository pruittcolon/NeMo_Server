import 'package:demo_ai_even/utils/app_logger.dart';
import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart'; // Import dotenv

class ApiDeepSeekService {
  late Dio _dio;

  ApiDeepSeekService() {
    _dio = Dio(
      BaseOptions(
        baseUrl: 'https://api.openai.com/v1',
        headers: {
          'Authorization': 'Bearer ${dotenv.env['OPENAI_API_KEY']}',
          'Content-Type': 'application/json',
        },
      ),
    );
  }

  Future<String> sendChatRequest(
    String question, {
    List<Map<String, String>>? conversationHistory,
    String? imageBase64,
  }) async {
    AppLogger.methodEntry('ApiDeepSeekService', 'sendChatRequest', params: {
      'question_length': question.length,
      'has_history': conversationHistory != null,
      'has_image': imageBase64 != null,
    });

    // 1. Determine which model to use based on keywords.
    String modelToUse;
    if (imageBase64 != null) {
      modelToUse = "gpt-4o"; // Vision requests must use a vision-capable model
      AppLogger.vision('Selected gpt-4o model for vision request');
    } else if (question.toLowerCase().contains("quickly")) {
      modelToUse = "gpt-4o-mini"; // Fast, lightweight text model
      AppLogger.debug('Selected gpt-4o-mini model (keyword: "quickly")');
    } else if (question.toLowerCase().contains("based on this exam question")) {
      // This is a refinement request from vision analysis - use best reasoning model
      modelToUse = "gpt-4.5-turbo"; // Best available reasoning model (use gpt-4o if 4.5 unavailable)
      AppLogger.debug('Selected gpt-4.5-turbo model for exam answer refinement');
    } else {
      modelToUse = "gpt-4o-mini"; // Default to a supported text model
      AppLogger.debug('Selected gpt-4o-mini model (default)');
    }

    // 2. Build messages array
    List<Map<String, dynamic>> messages;
    
    if (conversationHistory != null && conversationHistory.isNotEmpty) {
      AppLogger.debug('Using conversation history with ${conversationHistory.length} messages');
      messages = List<Map<String, dynamic>>.from(conversationHistory);
      
      // Ensure a clear vision-specific instruction when sending an image
      if (imageBase64 != null) {
        final hasSystem = messages.any((m) => m['role'] == 'system');
        if (!hasSystem) {
          messages.insert(0, {
            "role": "system",
            "content": "You are an exam assistant. Read any text, questions, or problems shown in images and provide brief, succinct answers. Answer directly in 40 words or less."
          });
        }
      }
      
      // Add current user message with optional image
      if (imageBase64 != null) {
        final imageSize = (imageBase64.length * 3 / 4 / 1024).toStringAsFixed(1);
        AppLogger.vision('Adding message with text and image ($imageSize KB)');
        messages.add({
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": question
            },
            {
              "type": "image_url",
              "image_url": {"url": "data:image/jpeg;base64,$imageBase64"}
            }
          ]
        });
      } else {
        AppLogger.debug('Adding text-only message to history');
        messages.add({"role": "user", "content": question});
      }
    } else {
      AppLogger.debug('Creating new conversation (no history)');
      // Simple request without history
      if (imageBase64 != null) {
        final imageSize = (imageBase64.length * 3 / 4 / 1024).toStringAsFixed(1);
        AppLogger.vision('Building vision request with image + prompt ($imageSize KB)');
        messages = [
          {
            "role": "system",
            "content": "You are an exam assistant. Read any text, questions, or problems shown in images and provide brief, succinct answers. Answer directly in 40 words or less."
          },
          {
            "role": "user",
            "content": [
              {
                "type": "text",
                "text": question
              },
              {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,$imageBase64"}
              }
            ]
          }
        ];
      } else {
        AppLogger.debug('Building text-only request');
        // Check if this is an exam refinement request
        final isExamRefinement = question.toLowerCase().contains("based on this exam question");
        final systemContent = isExamRefinement 
          ? "You are an expert exam tutor. Provide accurate, concise answers to exam questions. Be direct and brief (40 words max)."
          : "You are a helpful assistant.";
        
        messages = [
          {"role": "system", "content": systemContent},
          {"role": "user", "content": question}
        ];
      }
    }

    final data = {
      "model": modelToUse,
      "messages": messages,
      "max_tokens": imageBase64 != null ? 100 : 150, // Shorter for vision (exam answers)
      "temperature": imageBase64 != null ? 0.2 : 0.7, // Lower temp for factual exam answers
    };

    AppLogger.apiRequest('POST', '/chat/completions', data: {
      'model': modelToUse,
      'message_count': messages.length,
      'max_tokens': 150,
    });

    try {
      AppLogger.network('Sending request to OpenAI API...');
      final response = await _dio.post('/chat/completions', data: data);

      if (response.statusCode == 200) {
        AppLogger.apiResponse('/chat/completions', response.statusCode!);
        final data = response.data;
        final content = data['choices']?[0]?['message']?['content'] ??
            "Unable to answer the question";
        
        AppLogger.success('Received response: ${content.length} characters');
        AppLogger.debug('Response preview: ${content.substring(0, content.length > 100 ? 100 : content.length)}...');
        
        AppLogger.methodExit('ApiDeepSeekService', 'sendChatRequest', result: 'Success');
        return content;
      } else {
        AppLogger.apiResponse('/chat/completions', response.statusCode!);
        AppLogger.error('Request failed with status: ${response.statusCode}');
        return "Request failed with status: ${response.statusCode}";
      }
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final data = e.response?.data;
      
      if (status != null) {
        AppLogger.apiResponse('/chat/completions', status, data: data);
        AppLogger.error('OpenAI API error: $status', error: data);
        return "AI request error: $status, $data";
      } else {
        final message = e.message ?? e.error?.toString() ?? 'Unknown error';
        AppLogger.error('Network error during API request', error: e);
        return "AI request error: $message";
      }
    } catch (e, stackTrace) {
      AppLogger.error('Unexpected error in sendChatRequest', error: e, stackTrace: stackTrace);
      return "Unexpected error: $e";
    }
  }
}
