import 'package:dio/dio.dart';

class ApiService {
  late Dio _dio;

  ApiService() {
    _dio = Dio(
      BaseOptions(
        baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        headers: {
          'Authorization':
              'Bearer ${const String.fromEnvironment("DASHSCOPE_API_KEY", defaultValue: "Replace_With_API_Key_On_Official_EvenApp-Demo_on_Github")}', // replace with your apikey
          'Content-Type': 'application/json',
        },
      ),
    );
  }

  Future<String> sendChatRequest(String question) async {
    final data = {
      "model": "qwen-plus",
      "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": question}
      ],
    };
    print("sendChatRequest------data----------$data--------");

    try {
      final response = await _dio.post('/chat/completions', data: data);

      if (response.statusCode == 200) {
        print("Response: ${response.data}");

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
      }
      final message = e.message ?? e.error?.toString() ?? 'Unknown error';
      print("Error: $message");
      return "AI request error: $message";
    }
  }
}
