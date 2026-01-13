"""
Base Processor Interface
All processors (rule-based, LLM-based, AI-powered) inherit from this base class
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ProcessorType(Enum):
    """Processor type classification"""
    RULE_BASED = "rule-based"
    LLM_BASED = "llm-based"
    AI_POWERED = "ai-powered"


class ProcessorStatus(Enum):
    """Processing status"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseProcessor(ABC):
    """
    Base class for all processors

    All processors must implement:
    - process(): Main processing logic
    - validate(): Output validation
    """

    def __init__(self, processor_type: ProcessorType):
        """
        Args:
            processor_type: Type of processor (rule-based, llm-based, ai-powered)
        """
        self.processor_type = processor_type
        self.status = ProcessorStatus.IDLE
        self.error_message: Optional[str] = None
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing logic

        Args:
            input_data: Input data dictionary

        Returns:
            Output data dictionary

        Raises:
            Exception: If processing fails
        """
        pass

    @abstractmethod
    def validate(self, output_data: Dict[str, Any]) -> bool:
        """
        Validate processing output

        Args:
            output_data: Output data from process()

        Returns:
            True if valid, False otherwise
        """
        pass

    def get_status(self) -> ProcessorStatus:
        """Get current processing status"""
        return self.status

    def get_type(self) -> ProcessorType:
        """Get processor type"""
        return self.processor_type

    def get_error_message(self) -> Optional[str]:
        """Get error message if processing failed"""
        return self.error_message

    def reset(self):
        """Reset processor state"""
        self.status = ProcessorStatus.IDLE
        self.error_message = None
        self.logger.info(f"{self.__class__.__name__} reset to IDLE")

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute processing with error handling

        Args:
            input_data: Input data dictionary

        Returns:
            Output data dictionary

        Raises:
            Exception: If processing or validation fails
        """
        try:
            self.status = ProcessorStatus.RUNNING
            self.error_message = None
            self.logger.info(f"{self.__class__.__name__} started processing")

            # Run processing
            output_data = self.process(input_data)

            # Validate output
            if not self.validate(output_data):
                raise ValueError("Output validation failed")

            self.status = ProcessorStatus.COMPLETED
            self.logger.info(f"{self.__class__.__name__} completed successfully")

            return output_data

        except Exception as e:
            self.status = ProcessorStatus.FAILED
            self.error_message = str(e)
            self.logger.error(f"{self.__class__.__name__} failed: {e}")
            raise

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.processor_type.value}, status={self.status.value})"
