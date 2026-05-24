document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    const promptInput = document.getElementById('prompt');
    const terminalOutput = document.getElementById('terminal-output');
    const currentWorkflowSpan = document.getElementById('current-workflow-id');
    const statusPulse = document.getElementById('status-pulse');
    const workflowStatus = document.getElementById('workflow-status');
    const activeWorkflowPanel = document.getElementById('active-workflow-panel');
    const downloadBtn = document.getElementById('download-btn');
    const approvalModal = document.getElementById('approval-modal');
    const reviewSummary = document.getElementById('review-summary-content');
    
    let currentWorkflowId = null;

    function appendLog(message, type = 'system') {
        const div = document.createElement('div');
        div.className = `log ${type}`;
        div.textContent = `> ${message}`;
        terminalOutput.appendChild(div);
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }

    async function streamResponse(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.replace('data: ', '').trim();
                    if (!dataStr) continue;
                    
                    try {
                        const eventData = JSON.parse(dataStr);
                        
                        // Handle ping messages
                        if (eventData.message) {
                            appendLog(eventData.message, 'system');
                            continue; // skip further processing for this line
                        }

                        // Look for new log messages in execution_log (it might be in delta or state depending on the event type)
                        let logs = null;
                        if (eventData.delta && eventData.delta.execution_log) {
                            logs = eventData.delta.execution_log;
                        } else if (eventData.state && eventData.state.execution_log) {
                            logs = eventData.state.execution_log;
                        }
                        
                        if (logs && logs.length > 0) {
                            // Only append the very last log to prevent duplicate spams in UI
                            const latestLog = logs[logs.length - 1];
                            appendLog(latestLog, 'agent');
                        }
                        
                        // Set Workflow ID from stream
                        if (eventData.workflow_id && !currentWorkflowId) {
                            currentWorkflowId = eventData.workflow_id;
                            currentWorkflowSpan.textContent = currentWorkflowId;
                            activeWorkflowPanel.style.display = 'block';
                            downloadBtn.style.display = 'none';
                            statusPulse.style.backgroundColor = 'var(--accent)';
                        }

                        // Handle State changes
                        if (eventData.status) {
                            workflowStatus.textContent = eventData.status;
                            
                            if (eventData.status === 'awaiting_approval') {
                                showApprovalModal(eventData.state || {});
                            } else if (eventData.status === 'ready_for_deployment' || eventData.status === 'completed') {
                                statusPulse.style.backgroundColor = 'var(--success)';
                                downloadBtn.style.display = 'block';
                            }
                        }
                    } catch (e) {
                        console.error("Error parsing event:", e);
                    }
                }
            }
        }
    }

    document.getElementById('workflow-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const requestText = promptInput.value;
        if (!requestText) return;

        startBtn.disabled = true;
        terminalOutput.innerHTML = '';
        appendLog('Initializing multi-agent workflow...', 'highlight');
        
        try {
            const res = await fetch('/workflows/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_request: requestText, max_iterations: 3 })
            });
            
            await streamResponse(res);
            
        } catch (e) {
            appendLog(`Error: ${e.message}`, 'error');
        } finally {
            startBtn.disabled = false;
        }
    });

    function showApprovalModal(state) {
        approvalModal.style.display = 'flex';
        reviewSummary.textContent = "Generated Code Summary:\n" + (state.generated_code || "N/A") + "\n\nTest Cases:\n" + (state.test_cases || "N/A");
    }

    async function submitApproval(approved) {
        const feedback = document.getElementById('review-feedback').value;
        approvalModal.style.display = 'none';
        
        appendLog(`Human review submitted: ${approved ? 'APPROVED' : 'REJECTED'}`, 'highlight');
        
        try {
            const res = await fetch(`/workflows/${currentWorkflowId}/approval/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approved: approved, comment: feedback })
            });
            
            await streamResponse(res);
        } catch (e) {
            appendLog(`Error during approval: ${e.message}`, 'error');
        }
    }

    document.getElementById('approve-btn').addEventListener('click', () => submitApproval(true));
    document.getElementById('reject-btn').addEventListener('click', () => submitApproval(false));
    
    downloadBtn.addEventListener('click', () => {
        if (currentWorkflowId) {
            window.location.href = `/workflows/${currentWorkflowId}/download`;
        }
    });
});
