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

  Future<String> sendChatRequest(String question) async {
    // --- MODIFIED SECTION START ---

    // 1. Determine which model to use based on keywords.
    String modelToUse;
    if (question.toLowerCase().contains("quickly")) {
      modelToUse = "gpt-4o"; // Use GPT-4o for requests with "quickly"
    } else {
      modelToUse = "gpt-5"; // Use GPT-5 for all other requests
    }
    print("Keyword check complete. Using model: $modelToUse");

    // 2. Use the selected model in the request body.
    final data = {
      "model": modelToUse, // The model name is now dynamic
      "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": question}
      ],
    };

    // --- MODIFIED SECTION END ---

    print("Sending request to OpenAI with data: $data");

    try {
      final response = await _dio.post('/chat/completions', data: data);

      if (response.statusCode == 200) {
        print("OpenAI Response: ${response.data}");
        final data = response.data;
        final content = data['choices']?[0]?['message']?['content'] ??
            "Unable to answer the question";
        return content;
      } else {
        print("Request failed with status: ${response.statusCode}");
        return "Request failed with status: ${response.statusCode}";
      }
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final data = e.response?.data;
      if (status != null) {
        print("Error: $status, $data");
        return "AI request error: $status, $data";
      } else {
        final message = e.message ?? e.error?.toString() ?? 'Unknown error';
        print("Error: $message");
        return "AI request error: $message";
      }
    }
  }
}
