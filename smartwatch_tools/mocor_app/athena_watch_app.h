/**
 * athena_watch_app.h - Native UNISOC SC6531 Mocor OS Application Header
 * 
 * Target: UNISOC / Spreadtrum / Coolsand SC6531 (ARM9 / Mocor OS RTOS)
 * Display: 240x240 LCD GDI Engine
 * Radio & SIM: SIM GPRS PDP Context & Telegram Bot API Client
 */

#ifndef __ATHENA_WATCH_APP_H__
#define __ATHENA_WATCH_APP_H__

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Mocor OS SDK Header Stubs */
typedef unsigned char   uint8;
typedef unsigned short  uint16;
typedef unsigned int    uint32;
typedef signed int      int32;
typedef unsigned char   BOOLEAN;

#ifndef TRUE
#define TRUE  1
#define FALSE 0
#endif

/* Screen Identifiers (Matching Diagram) */
typedef enum {
    ATHENA_SCR_TASKS = 0,     /* Screen 1: Default Tasks View (Time, Tasks, 1, 2, 3 list) */
    ATHENA_SCR_LISTENING,     /* Screen 2: Listening View (Large circle, active while holding button) */
    ATHENA_SCR_REPLY          /* Screen 3: Question & Answer View (Question, Ans, Read Aloud & OK) */
} ATHENA_SCREEN_ID_E;

/* SIM Card Network States */
typedef enum {
    SIM_STATE_ABSENT = 0,
    SIM_STATE_PIN_LOCKED,
    SIM_STATE_REGISTERED,
    SIM_STATE_GPRS_CONNECTED
} SIM_NETWORK_STATE_E;

/* Side Key Event Identifiers */
#define KEY_SIDE_FLASHLIGHT   0x4A   /* Physical hardware side button keycode */
#define KEY_EVENT_DOWN        0x01
#define KEY_EVENT_UP          0x02
#define HOLD_THRESHOLD_MS     250

/* Task Item Structure */
typedef struct {
    uint32 id;
    char   title[64];
    BOOLEAN is_completed;
} ATHENA_TASK_T;

#define MAX_ATHENA_TASKS      5

/* Global Application Context */
typedef struct {
    ATHENA_SCREEN_ID_E  current_screen;
    SIM_NETWORK_STATE_E sim_state;
    
    uint32              press_start_time;
    BOOLEAN             is_holding_button;
    
    char                apn[32];
    char                question_buffer[256];
    char                answer_buffer[512];
    
    ATHENA_TASK_T       tasks[MAX_ATHENA_TASKS];
    uint8               task_count;
    
    char                telegram_bot_token[128];
    char                telegram_chat_id[64];
} ATHENA_APP_CTX_T;

/* Function Prototypes */
void Athena_AppInit(void);
void Athena_InitSIMCardGPRS(void);
void Athena_HandleSideKeyEvent(uint8 key_code, uint8 event_type, uint32 timestamp_ms);

void Athena_DrawScreen1_Tasks(void);
void Athena_DrawScreen2_Listening(void);
void Athena_DrawScreen3_Reply(void);

void Athena_StartVoiceRecording(void);
void Athena_StopVoiceRecordingAndSend(void);

void Athena_SendSIMTelegramHTTP(const char *text_prompt);
void Athena_OnTelegramHTTPResponse(const char *json_response);

void Athena_ActionReadAloud(void);
void Athena_ActionOK(void);

#endif /* __ATHENA_WATCH_APP_H__ */
