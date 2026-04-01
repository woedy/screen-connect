"""
WebSocket consumer for real-time screen sharing sessions.

Handles:
- Token-based authentication
- Role enforcement (agent vs client)
- Binary frame relay from client → agent (zero-copy, no JSON parse)
- JSON control message relay for input, files, terminal, system tools
- Session lifecycle management
"""
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = 1
FRAME_BINARY_TYPES = {0x01, 0x04}  # full-frame + tiled-frame

# Message types routed from agent → client
AGENT_TO_CLIENT_TYPES = {
    # Input commands
    "mouse_click", "mouse_move", "key_press", "scroll",
    "mouse_down", "mouse_up",
    # File management
    "file_list", "file_download_request", "file_upload_start",
    "file_upload_chunk", "file_upload_complete", "file_delete",
    # Remote terminal
    "command_run", "command_kill",
    # System tools
    "system_info_request", "process_list_request", "process_kill",
    "clipboard_get", "clipboard_set",
    # Bandwidth controls
    "bandwidth_mode", "streaming_toggle", "request_keyframe",
    # System actions & Camera
    "system_action", "camera_snapshot_request", "privacy_screen",
}

# Message types routed from client → agent
CLIENT_TO_AGENT_TYPES = {
    # Screen data
    "frame", "screen_info",
    # File management responses
    "file_list_response", "file_list_chunk", "file_list_complete",
    "file_download_start", "file_download_complete",
    "file_download_error", "file_upload_ready", "file_upload_success",
    "file_upload_error", "file_delete_response",
    # Remote terminal output
    "command_output", "command_complete",
    # System tools responses
    "system_info", "process_list", "process_kill_response",
    "clipboard_content", "clipboard_set_response",
    "camera_snapshot_response",
}


class ScreenShareConsumer(AsyncWebsocketConsumer):
    """
    WebSocket endpoint: /ws/session/{session_id}/?token=xxx&role=agent|client

    Groups:
    - session_{session_id}_agent  — only the agent receives frames here
    - session_{session_id}_client — only the client receives input commands here

    Message flow:
    - Client sends 'frame' → relayed to agent group only
    - Client sends binary → relayed to agent group as-is (zero-copy)
    - Agent sends input/file/terminal/system commands → relayed to client group
    - 'session_end' from either party → terminates session
    - 'ping' / 'pong' for keepalive
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.role = None
        self.session = None
        self.agent_frame_group = None
        self.agent_control_group = None
        self.client_frame_group = None
        self.client_control_group = None

    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.role = self.scope.get("role")
        self.session = self.scope.get("support_session")

        self.agent_frame_group = f"session_{self.session_id}_agent_frame"
        self.agent_control_group = f"session_{self.session_id}_agent_control"
        self.client_frame_group = f"session_{self.session_id}_client_frame"
        self.client_control_group = f"session_{self.session_id}_client_control"

        # Reject if no valid session
        if not self.session:
            logger.warning(f"WS rejected: invalid session/token for {self.session_id}")
            await self.close(code=4001)
            return

        # Reject if invalid role
        if self.role not in ("agent", "client"):
            logger.warning(f"WS rejected: invalid role '{self.role}'")
            await self.close(code=4002)
            return

        # Enforce single client per session
        if self.role == "client" and self.session.client_connected:
            logger.warning(f"WS rejected: client already connected to {self.session_id}")
            await self.close(code=4003)
            return

        # Enforce single agent per session
        if self.role == "agent" and self.session.agent_connected:
            logger.warning(f"WS rejected: agent already connected to {self.session_id}")
            await self.close(code=4004)
            return

        # Join the appropriate group
        if self.role == "agent":
            await self.channel_layer.group_add(self.agent_frame_group, self.channel_name)
            await self.channel_layer.group_add(self.agent_control_group, self.channel_name)
            await self._set_agent_connected(True)
        else:
            await self.channel_layer.group_add(self.client_frame_group, self.channel_name)
            await self.channel_layer.group_add(self.client_control_group, self.channel_name)
            await self._set_client_connected(True)

        await self.accept()
        
        # 1. Notify the OTHER party that we've joined
        await self._notify_connection_status("connected")
        
        # 2. ALSO notify OURSELVES of the current other party state 
        # (Needed because the other party might already be here)
        peer_status = "connected" if (
            (self.role == "agent" and self.session.client_connected) or
            (self.role == "client" and self.session.agent_connected)
        ) else "waiting"
        
        await self.send(text_data=json.dumps({
            "type": "connection_status",
            "role": "client" if self.role == "agent" else "agent",
            "status": peer_status,
        }))

        logger.info(f"WS connected: {self.role} to session {self.session_id} (peer={peer_status})")

    async def disconnect(self, close_code):
        if not self.session_id or not self.role:
            return

        # Leave group
        if self.role == "agent":
            await self.channel_layer.group_discard(self.agent_frame_group, self.channel_name)
            await self.channel_layer.group_discard(self.agent_control_group, self.channel_name)
            await self._set_agent_connected(False)
        else:
            await self.channel_layer.group_discard(self.client_frame_group, self.channel_name)
            await self.channel_layer.group_discard(self.client_control_group, self.channel_name)
            await self._set_client_connected(False)

        # Notify the other party
        await self._notify_connection_status("disconnected")

        logger.info(f"WS disconnected: {self.role} from session {self.session_id} (code={close_code})")

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages."""
        if bytes_data:
            # Binary data — route frame payloads separately from control/file payloads
            msg_type = bytes_data[0] if len(bytes_data) > 0 else None
            is_frame = msg_type in FRAME_BINARY_TYPES

            if self.role == "client":
                # Python agent -> dashboard
                target_group = self.agent_frame_group if is_frame else self.agent_control_group
                await self.channel_layer.group_send(
                    target_group,
                    {
                        "type": "relay.binary",
                        "data": bytes_data,
                    },
                )
            elif self.role == "agent":
                # Dashboard -> Python agent
                target_group = self.client_frame_group if is_frame else self.client_control_group
                await self.channel_layer.group_send(
                    target_group,
                    {
                        "type": "relay.binary",
                        "data": bytes_data,
                    },
                )
            return

        if text_data:
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError:
                await self.send(text_data=json.dumps({"error": "Invalid JSON"}))
                return

            msg_type = data.get("type")
            msg_version = data.get("v", PROTOCOL_VERSION)

            if msg_version != PROTOCOL_VERSION:
                await self.send(text_data=json.dumps({
                    "type": "error",
                    "error": f"Unsupported protocol version: {msg_version}",
                    "supported_version": PROTOCOL_VERSION,
                }))
                return

            if msg_type == "ping":
                await self.send(text_data=json.dumps({"type": "pong"}))
                return

            if msg_type == "session_end":
                await self._handle_session_end()
                return

            if self.role == "client":
                await self._handle_client_message(data, msg_type)
            elif self.role == "agent":
                await self._handle_agent_message(data, msg_type)

    async def _handle_client_message(self, data, msg_type):
        """Route messages from Python agent (role=client) → dashboard (sits in agent_group)."""
        if msg_type in CLIENT_TO_AGENT_TYPES:
            await self.channel_layer.group_send(
                self.agent_control_group,
                {
                    "type": "relay.message",
                    "message": data,
                },
            )

    async def _handle_agent_message(self, data, msg_type):
        """Route messages from dashboard (role=agent) → Python agent (sits in client_group)."""
        if msg_type in AGENT_TO_CLIENT_TYPES:
            await self.channel_layer.group_send(
                self.client_control_group,
                {
                    "type": "relay.message",
                    "message": data,
                },
            )

    async def _handle_session_end(self):
        """End the session and notify both parties."""
        await self._end_session_db()

        # Notify both groups
        end_msg = {"type": "relay.message", "message": {"type": "session_ended"}}
        await self.channel_layer.group_send(self.agent_control_group, end_msg)
        await self.channel_layer.group_send(self.client_control_group, end_msg)

    async def _notify_connection_status(self, status):
        """Notify the other party about connection status changes."""
        message = {
            "type": "relay.message",
            "message": {
                "type": "connection_status",
                "role": self.role,
                "status": status,
            },
        }

        # Python agent (role=client) connects → notify dashboard (sits in agent_group)
        # Dashboard (role=agent) connects → notify Python agent (sits in client_group)
        if self.role == "client":
            await self.channel_layer.group_send(self.agent_control_group, message)
        else:
            await self.channel_layer.group_send(self.client_control_group, message)

    # -------------------------------------------------------------------------
    # Channel layer event handlers
    # -------------------------------------------------------------------------

    async def relay_message(self, event):
        """Relay a JSON message to this WebSocket."""
        await self.send(text_data=json.dumps(event["message"]))

    async def relay_binary(self, event):
        """Relay binary data to this WebSocket."""
        await self.send(bytes_data=event["data"])

    # -------------------------------------------------------------------------
    # Database helpers (sync → async wrappers)
    # -------------------------------------------------------------------------

    @database_sync_to_async
    def _set_client_connected(self, connected):
        from sessions_app.models import SupportSession

        try:
            session = SupportSession.objects.get(id=self.session_id)
            session.client_connected = connected
            if connected and session.status == SupportSession.Status.WAITING:
                session.status = SupportSession.Status.ACTIVE
            session.save(update_fields=["client_connected", "status"])
        except SupportSession.DoesNotExist:
            pass

    @database_sync_to_async
    def _set_agent_connected(self, connected):
        from sessions_app.models import SupportSession

        try:
            session = SupportSession.objects.get(id=self.session_id)
            session.agent_connected = connected
            session.save(update_fields=["agent_connected"])
        except SupportSession.DoesNotExist:
            pass

    @database_sync_to_async
    def _end_session_db(self):
        from sessions_app.models import SupportSession

        try:
            session = SupportSession.objects.get(id=self.session_id)
            session.end_session()
        except SupportSession.DoesNotExist:
            pass
