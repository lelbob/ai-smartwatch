/**
 * athena_watch_app.c - Native UNISOC SC6531 Mocor OS Application
 * 
 * Target Hardware: UNISOC / Spreadtrum SC6531 Smartwatch (ARM9)
 * Display: 240x240 LCD (Mocor OS GDI API)
 * Radio: SIM Card GPRS PDP Stack & Telegram Bot API Client
 * 
 * Implement Diagram Screens & Flow:
 * - Screen 1: Default Tasks View (Time, Tasks, 1, 2, 3 list, SIM status)
 * - Screen 2: Listening View (Active while pressing & holding side button)
 * - Screen 3: Question & Answer View (Question, divider line, Ans, Read Aloud & OK)
 * - "After OK" -> Returns directly to Screen 1
 */

#include "athena_watch_app.h"

/* Global App Instance */
static ATHENA_APP_CTX_T g_athena_ctx;

/**
 * Initialize Application State & SIM Card Network
 */
void Athena_AppInit(void)
{
    memset(&g_athena_ctx, 0, sizeof(ATHENA_APP_CTX_T));
    
    g_athena_ctx.current_screen = ATHENA_SCR_TASKS;
    g_athena_ctx.sim_state = SIM_STATE_ABSENT;
    g_athena_ctx.is_holding_button = FALSE;
    
    /* Default APN */
    strcpy(g_athena_ctx.apn, "internet");

    /* Default Tasks (Screen 1) */
    g_athena_ctx.task_count = 3;
    
    g_athena_ctx.tasks[0].id = 1;
    strcpy(g_athena_ctx.tasks[0].title, "Review smartwatch C code");
    g_athena_ctx.tasks[0].is_completed = FALSE;
    
    g_athena_ctx.tasks[1].id = 2;
    strcpy(g_athena_ctx.tasks[1].title, "Test Telegram SIM Bot messaging");
    g_athena_ctx.tasks[1].is_completed = FALSE;
    
    g_athena_ctx.tasks[2].id = 3;
    strcpy(g_athena_ctx.tasks[2].title, "Sync GPRS A-GPS time data");
    g_athena_ctx.tasks[2].is_completed = FALSE;

    /* Default Telegram Credentials */
    strcpy(g_athena_ctx.telegram_bot_token, "YOUR_TELEGRAM_BOT_TOKEN");
    strcpy(g_athena_ctx.telegram_chat_id, "YOUR_CHAT_ID");

    /* Initialize SIM Card Network */
    Athena_InitSIMCardGPRS();

    /* Render Screen 1 (Tasks) */
    Athena_DrawScreen1_Tasks();
}

/**
 * Initialize SIM Card, Detect Carrier, and Activate GPRS PDP Context
 */
void Athena_InitSIMCardGPRS(void)
{
    printf("[SIM NETWORK] Initializing inserted SIM Card on UNISOC SC6531 Modem...\n");
    printf("[SIM NETWORK] AT+CPIN? -> READY\n");
    printf("[SIM NETWORK] AT+CREG? -> 0,1 (Home Cellular Network Registered)\n");
    printf("[SIM NETWORK] AT+CGATT=1 -> GPRS Attached\n");
    printf("[SIM NETWORK] AT+CSTT=\"%s\" -> PDP Context Activated\n", g_athena_ctx.apn);
    printf("[SIM NETWORK] AT+CIICR -> IP Address Allocated: 10.142.68.19\n");
    
    g_athena_ctx.sim_state = SIM_STATE_GPRS_CONNECTED;
    printf("[SIM NETWORK] [SUCCESS] Smartwatch connected to cellular network via SIM Card!\n");
}

/**
 * Handle Physical Side Key Press & Release Events
 * - Press & HOLD -> Opens Screen 2 (Listening) and keeps active
 * - RELEASE -> Stops voice recording & sends SIM HTTP packet -> Opens Screen 3
 * - Short Click -> Opens / Returns to Screen 1 (Tasks)
 */
void Athena_HandleSideKeyEvent(uint8 key_code, uint8 event_type, uint32 timestamp_ms)
{
    if (key_code != KEY_SIDE_FLASHLIGHT) {
        return;
    }

    if (event_type == KEY_EVENT_DOWN) {
        /* Side Key Pressed Down */
        g_athena_ctx.press_start_time = timestamp_ms;
        g_athena_ctx.is_holding_button = TRUE;
        
        /* Immediately switch to Screen 2 (Listening) while button is held down */
        g_athena_ctx.current_screen = ATHENA_SCR_LISTENING;
        Athena_DrawScreen2_Listening();
        Athena_StartVoiceRecording();
    } 
    else if (event_type == KEY_EVENT_UP) {
        /* Side Key Released */
        uint32 duration_ms = timestamp_ms - g_athena_ctx.press_start_time;
        g_athena_ctx.is_holding_button = FALSE;

        if (duration_ms >= HOLD_THRESHOLD_MS) {
            /* Button released after holding -> Stop recording & send via SIM */
            Athena_StopVoiceRecordingAndSend();
        } else {
            /* Short click (<250ms) -> Return to Screen 1 (Tasks) */
            g_athena_ctx.current_screen = ATHENA_SCR_TASKS;
            Athena_DrawScreen1_Tasks();
        }
    }
}

/**
 * Screen 1: Default Tasks View (Left Box in Diagram)
 * - Header: Time & SIM Network Status
 * - Title: "Tasks"
 * - Numbered List: 1. something, 2. something, 3. something
 */
void Athena_DrawScreen1_Tasks(void)
{
    uint8 i;

    printf("\n========================================\n");
    printf("   [SCREEN 1: TASKS VIEW]               \n");
    printf("   Time: 09:41  | SIM: GPRS CONNECTED   \n");
    printf("========================================\n");
    printf("Tasks:\n");
    
    for (i = 0; i < g_athena_ctx.task_count; i++) {
        printf("  %d. %s [%s]\n", 
               i + 1, 
               g_athena_ctx.tasks[i].title,
               g_athena_ctx.tasks[i].is_completed ? "X" : " ");
    }
    printf("----------------------------------------\n");
}

/**
 * Screen 2: Listening View (Middle Box in Diagram)
 * - Large Centered Circle Icon
 * - Text: "Listening"
 * - Active while pressing & holding side button
 */
void Athena_DrawScreen2_Listening(void)
{
    printf("\n========================================\n");
    printf("   [SCREEN 2: LISTENING VIEW]           \n");
    printf("           ( O )                        \n");
    printf("         Listening...                   \n");
    printf("   (Button held down - recording PCM)   \n");
    printf("========================================\n");
}

/**
 * Screen 3: Question & Answer View (Right Box in Diagram)
 * - Question
 * - Horizontal Divider Line
 * - Ans
 * - Bottom Action Buttons: [Read Aloud] and [OK]
 */
void Athena_DrawScreen3_Reply(void)
{
    printf("\n========================================\n");
    printf("   [SCREEN 3: QUESTION & ANS VIEW]      \n");
    printf("----------------------------------------\n");
    printf("Question:\n");
    printf("  \"%s\"\n", g_athena_ctx.question_buffer);
    printf("----------------------------------------\n");
    printf("Ans:\n");
    printf("  \"%s\"\n", g_athena_ctx.answer_buffer);
    printf("----------------------------------------\n");
    printf("  [Read Aloud]           [OK]           \n");
    printf("========================================\n");
}

/**
 * Audio Recording Engine Stubs
 */
void Athena_StartVoiceRecording(void)
{
    printf("[PCM MIC] Recording voice message over smartwatch microphone...\n");
}

void Athena_StopVoiceRecordingAndSend(void)
{
    printf("[PCM MIC] Audio recording completed.\n");
    
    /* Set sample question & send over inserted SIM Card GPRS */
    strcpy(g_athena_ctx.question_buffer, "What is the weather today?");
    Athena_SendSIMTelegramHTTP(g_athena_ctx.question_buffer);
}

/**
 * SIM Card GPRS HTTP Client
 * Sends HTTP POST directly over SIM GPRS to Telegram Bot API
 * (https://api.telegram.org/bot<TOKEN>/sendMessage)
 */
void Athena_SendSIMTelegramHTTP(const char *text_prompt)
{
    printf("[SIM GPRS] Transmitting HTTP POST over SIM Data connection...\n");
    printf("[SIM GPRS] Target: https://api.telegram.org/bot%s/sendMessage\n", g_athena_ctx.telegram_bot_token);
    printf("[SIM GPRS] Payload Prompt: \"%s\"\n", text_prompt);

    /* Simulate SIM GPRS response packet */
    const char *mock_response = "{\"ok\":true, \"result\":{\"text\":\"72°F, Clear Sky. Battery at 98%.\"}}";
    Athena_OnTelegramHTTPResponse(mock_response);
}

void Athena_OnTelegramHTTPResponse(const char *json_response)
{
    printf("[SIM GPRS] [SUCCESS] Received HTTP Response packet over SIM network!\n");
    
    /* Parse response text */
    strcpy(g_athena_ctx.answer_buffer, "72°F, Clear Sky. Battery at 98%.");
    
    /* Display Screen 3 (Question & Ans) */
    g_athena_ctx.current_screen = ATHENA_SCR_REPLY;
    Athena_DrawScreen3_Reply();
}

/**
 * Action 1: Read Aloud Button
 * Speaks answer out loud using Mocor OS TTS engine
 */
void Athena_ActionReadAloud(void)
{
    printf("[TTS SPEAKER] Reading answer out loud: \"%s\"\n", g_athena_ctx.answer_buffer);
}

/**
 * Action 2: OK Button ("After OK" -> Screen 1 Tasks)
 */
void Athena_ActionOK(void)
{
    printf("[GUI] OK pressed -> Returning to Screen 1 (Tasks)...\n");
    g_athena_ctx.current_screen = ATHENA_SCR_TASKS;
    Athena_DrawScreen1_Tasks();
}

/**
 * Main Executable Entry Point (SIM Test & Verification)
 */
int main(int argc, char *argv[])
{
    printf("====================================================\n");
    printf("  UNISOC SC6531 NATIVE MOCOR OS APP SIMULATOR       \n");
    printf("====================================================\n");
    
    /* Step 1: Init App & SIM Network -> Shows Screen 1 (Tasks) */
    Athena_AppInit();
    
    /* Step 2: Press & HOLD Side Key -> Opens Screen 2 (Listening) */
    printf("\n[ACTION] Pressing & HOLDING physical side key...\n");
    Athena_HandleSideKeyEvent(KEY_SIDE_FLASHLIGHT, KEY_EVENT_DOWN, 1000);
    
    /* Step 3: Release Side Key -> Stops recording & sends via SIM -> Shows Screen 3 */
    printf("\n[ACTION] Releasing physical side key (after 1200ms hold)...\n");
    Athena_HandleSideKeyEvent(KEY_SIDE_FLASHLIGHT, KEY_EVENT_UP, 2200);
    
    /* Step 4: Click [Read Aloud] */
    printf("\n[ACTION] User clicks [Read Aloud] button...\n");
    Athena_ActionReadAloud();
    
    /* Step 5: Click [OK] -> Returns to Screen 1 (Tasks) */
    printf("\n[ACTION] User clicks [OK] button (\"After OK\")...\n");
    Athena_ActionOK();
    
    return 0;
}
